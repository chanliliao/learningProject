"""
LLM client utilities: model factory, structured-output runner, and Langfuse tracing.

All LLM interactions in the pipeline pass through ``run_structured``, which handles
timing, token counting, cost estimation, and optional Langfuse trace emission in a
single place.  Agent construction uses ``build_agent`` or ``_model`` directly.
"""

import time
from functools import lru_cache
from typing import TypeVar
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlmodel.ext.asyncio.session import AsyncSession
from app.config import get_settings
from app.models.audit import LLMCall

T = TypeVar("T", bound=BaseModel)

# Approximate pricing per 1K tokens (input, output) for common OpenRouter models.
# Used for cost estimation only — never for billing.  Falls back to a generic rate
# for models not listed here.
_COST_PER_1K: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.005, 0.015),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "claude-3-haiku": (0.00025, 0.00125),
    "claude-3-sonnet": (0.003, 0.015),
}


def _estimate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate the USD cost of a single LLM call.

    Matches ``model_name`` against the keys in ``_COST_PER_1K`` via a substring search
    (case-insensitive).  Falls back to a conservative generic rate when no match is
    found.

    Args:
        model_name: Model identifier string returned by pydantic-ai (e.g.
            ``"openai/gpt-4o-mini"``).
        prompt_tokens: Number of input tokens used.
        completion_tokens: Number of output tokens generated.

    Returns:
        Estimated cost in USD as a float.  Accuracy depends on ``_COST_PER_1K`` being
        up to date.
    """
    name = model_name.lower()
    for key, (in_rate, out_rate) in _COST_PER_1K.items():
        if key in name:
            return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1000
    return (prompt_tokens * 0.001 + completion_tokens * 0.002) / 1000


def _model(mode: str | None = None):
    """Return a pydantic-ai model instance for the configured provider.

    When ``mode`` or ``Settings.llm_mode`` is ``"test"``, returns a ``TestModel``
    that generates synthetic responses without making real API calls.  Otherwise
    returns an ``OpenAIModel`` pointed at the OpenRouter API.

    Args:
        mode: Override for the LLM mode.  ``"test"`` → ``TestModel``.
            ``None`` reads from ``Settings.llm_mode``.

    Returns:
        A pydantic-ai model instance compatible with ``Agent``.
    """
    s = get_settings()
    if (mode or s.llm_mode) == "test":
        return TestModel()
    return OpenAIModel(
        s.openrouter_model,
        provider=OpenAIProvider(base_url=s.openrouter_base_url, api_key=s.openrouter_api_key),
    )


def build_agent(output_type: type[T], system: str, mode: str | None = None) -> Agent:
    """Construct a pydantic-ai ``Agent`` with a structured output type.

    Convenience wrapper around ``Agent`` for simple one-shot structured output use
    cases.  For agents that need tools or dependency injection, construct ``Agent``
    directly.

    Args:
        output_type: Pydantic model class the LLM must produce.
        system: System prompt string.
        mode: LLM mode override.

    Returns:
        A configured ``Agent`` instance ready to call with ``agent.run()``.
    """
    return Agent(_model(mode), output_type=output_type, system_prompt=system)


@lru_cache(maxsize=1)
def get_langfuse():
    """Return a cached Langfuse client, or ``None`` if credentials are not configured.

    Langfuse is optional — if the public/secret key settings are empty or the
    ``langfuse`` package is not installed, this returns ``None`` and tracing is
    silently disabled.

    Returns:
        A ``Langfuse`` instance if credentials are set and the package is available,
        otherwise ``None``.
    """
    s = get_settings()
    if not s.langfuse_public_key or not s.langfuse_secret_key:
        return None
    try:
        from langfuse import Langfuse
        return Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=s.langfuse_host,
        )
    except Exception:
        return None


async def run_structured(
    agent: Agent,
    user: str,
    *,
    stage: str,
    run_id: int | None,
    session: AsyncSession | None,
    deps: object = None,
) -> BaseModel:
    """Run a pydantic-ai agent and persist a full ``LLMCall`` audit record.

    Executes the agent, measures wall-clock latency, reads token usage from the result,
    emits an optional Langfuse trace, and saves a ``LLMCall`` row to the DB if a
    session is provided.

    Args:
        agent: Configured pydantic-ai ``Agent`` instance.
        user: User-turn prompt string.
        stage: Pipeline stage label (e.g. ``"extract"``, ``"map"``), stored on the
            ``LLMCall`` row for analytics.
        run_id: Owning ``PipelineRun`` ID for the ``LLMCall`` foreign key.  Pass
            ``None`` to skip run association (e.g. health-check pings).
        session: Active async SQLModel session for saving the ``LLMCall`` record.
            Pass ``None`` to skip DB logging entirely.
        deps: Dependency object injected into the agent for tool calls.  ``None`` for
            agents that use no tools.

    Returns:
        The structured output object produced by the agent (a subclass of
        ``BaseModel``).
    """
    start = time.monotonic()
    result = await agent.run(user, deps=deps) if deps is not None else await agent.run(user)
    latency_ms = int((time.monotonic() - start) * 1000)
    usage = result.usage

    trace_id = None
    lf = get_langfuse()
    if lf is not None:
        try:
            trace = lf.trace(name=stage, input=user, output=str(result.output))
            trace_id = trace.id
            lf.flush()
        except Exception:
            pass

    if session is not None:
        prompt_tokens = getattr(usage, "input_tokens", 0) or 0
        completion_tokens = getattr(usage, "output_tokens", 0) or 0
        session.add(LLMCall(
            run_id=run_id,
            stage=stage,
            model=str(agent.model),
            prompt=user,
            response=str(result.output),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            estimated_cost=_estimate_cost(str(agent.model), prompt_tokens, completion_tokens),
            langfuse_trace_id=trace_id,
        ))
    return result.output


async def ping_llm(mode: str | None = None) -> str:
    """Send a minimal prompt to the LLM to verify connectivity.

    Used by the ``/api/health/llm`` endpoint.  Returns the model's reply string.

    Args:
        mode: LLM mode override.

    Returns:
        Short greeting string from the model.
    """
    agent = Agent(_model(mode), output_type=str, system_prompt="Reply with a short greeting.")
    result = await agent.run("Say hello in five words or fewer.")
    return result.output
