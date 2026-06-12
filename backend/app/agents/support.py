"""
Support agent: answers questions about a completed pipeline run.

Uses a RAG retriever backed by Qdrant to find relevant context from the run's
indexed mappings, then passes that context to a pydantic-ai agent that can also
look up live ``FieldMapping`` rows via the ``lookup_mapping`` tool.

The agent may propose field-level edits via ``proposed_edits`` in its output.
Those edits are not applied automatically — they flow through the ``/support/apply``
endpoint where a human reviewer approves or rejects them.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic_ai import Agent, RunContext
from app.llm.client import _model, run_structured
from app.rag.index import query_run


_SYSTEM = (
    "You are a helpful integration engineer assistant. You have access to details about a completed "
    "data pipeline run including field mappings, audit notes, and interpretations. "
    "Answer questions about why specific mappings were made, citing the context provided. "
    "Use the lookup_mapping tool to fetch field details from the database. "
    "When proposing a remapping, include it in the proposed_edits output field with the field id, "
    "new target path, and reason."
)


class EditIntent(BaseModel):
    """A field-remapping proposal emitted by the support agent.

    Attributes:
        run_id: The pipeline run this edit applies to.
        field_id: Primary key of the ``FieldMapping`` row to update.
        new_target_path: Replacement target schema field name.
        new_transform: Replacement transform name, or ``None`` to keep the current one.
        reason: Human-readable explanation of why the remapping is suggested.
    """

    run_id: int
    field_id: int
    new_target_path: str
    new_transform: str | None = None
    reason: str


class SupportAnswer(BaseModel):
    """Structured output returned by the support agent for every question.

    Attributes:
        answer: Plain-text answer to the user's question.
        proposed_edits: Zero or more ``EditIntent`` objects the agent recommends.
            The UI surfaces these as one-click "Apply" buttons; clicking POSTs to
            ``/runs/{id}/support/apply`` which queues the edit for human review.
    """

    answer: str
    proposed_edits: list[EditIntent] = []


@dataclass
class _Deps:
    """Dependency container injected into the pydantic-ai agent at run time.

    Attributes:
        session: Active async SQLModel session for ``lookup_mapping`` DB queries.
            ``None`` in unit tests or when DB access is not required.
        run_id: The pipeline run being queried.
    """

    session: AsyncSession | None
    run_id: int


def _build_support_agent(mode: str | None = None) -> Agent[_Deps, SupportAnswer]:
    """Construct the pydantic-ai support agent with the ``lookup_mapping`` tool wired in.

    The agent is built fresh on every call (not cached) because the ``mode`` parameter
    determines which underlying model is used — caching would ignore mode changes.

    Args:
        mode: LLM mode override.  ``"test"`` uses ``TestModel``; ``None`` reads
            ``Settings.llm_mode``.

    Returns:
        A configured ``Agent[_Deps, SupportAnswer]`` ready to call ``agent.run()``.
    """
    agent: Agent[_Deps, SupportAnswer] = Agent(
        _model(mode),
        output_type=SupportAnswer,
        system_prompt=_SYSTEM,
        deps_type=_Deps,
    )

    @agent.tool
    async def lookup_mapping(ctx: RunContext[_Deps], field_name: str) -> str:
        """Fetch live ``FieldMapping`` rows from the DB that match a field name.

        The agent calls this tool when it needs runtime mapping details that may not
        be in the RAG context (e.g. exact IDs needed to populate ``proposed_edits``).

        Args:
            ctx: pydantic-ai run context carrying the ``_Deps`` instance.
            field_name: Partial name to match against ``source_path`` or ``target_path``
                (case-insensitive substring match).

        Returns:
            A newline-delimited string of matching mappings, or a no-match message.
        """
        if ctx.deps.session is None:
            return "No DB access."
        from app.models.mapping import FieldMapping
        results = await ctx.deps.session.exec(
            select(FieldMapping).where(FieldMapping.run_id == ctx.deps.run_id)
        )
        mappings = results.all()
        name_lower = field_name.lower()
        match = [
            m for m in mappings
            if name_lower in m.source_path.lower() or name_lower in m.target_path.lower()
        ]
        if not match:
            return f"No mappings found for '{field_name}'."
        return "\n".join(
            f"id={m.id} {m.source_path} -> {m.target_path} "
            f"(confidence={m.confidence}, status={m.status})"
            for m in match
        )

    return agent


async def answer_question(
    run_id: int,
    question: str,
    session: AsyncSession | None,
    *,
    retriever: Callable[..., Any] | None = None,
    client: Any | None = None,
    embed_model: Any | None = None,
    mode: str | None = None,
) -> SupportAnswer:
    """Answer a natural-language question about a pipeline run using RAG + LLM.

    Retrieves relevant context from the run's Qdrant index, prepends it to the prompt,
    and calls the support agent.  The agent may also call ``lookup_mapping`` for live
    DB lookups during its reasoning.

    Args:
        run_id: ID of the ``PipelineRun`` being queried.
        question: Free-text question from the user.
        session: Active async SQLModel session passed to ``_Deps`` for tool use.
            Pass ``None`` to disable DB lookups.
        retriever: Optional override for the RAG retrieval function.  Primarily used in
            tests to inject a mock.  Must accept ``(run_id, question, client=...,
            embed_model=...)`` and return a list of ``NodeWithScore`` objects.
        client: Qdrant client instance to pass to the retriever.  ``None`` uses the
            default client from ``_get_client()``.
        embed_model: Embedding model to pass to the retriever.  ``None`` uses the
            default from ``_get_embed_model()``.
        mode: LLM mode override.

    Returns:
        A ``SupportAnswer`` containing the text answer and any proposed edits.
    """
    if retriever is not None:
        nodes = retriever(run_id, question, client=client, embed_model=embed_model)
    else:
        nodes = query_run(run_id, question, client=client, embed_model=embed_model)

    context = "\n".join(n.text for n in nodes) if nodes else "No context available."

    user_msg = (
        f"Run ID: {run_id}\n\n"
        f"Context from the pipeline run:\n{context}\n\n"
        f"Question: {question}"
    )

    agent = _build_support_agent(mode=mode)
    deps = _Deps(session=session, run_id=run_id)
    return await run_structured(
        agent, user_msg, stage="support", run_id=run_id, session=session, deps=deps
    )


def propose_edit(
    run_id: int,
    field_id: int,
    new_target_path: str,
    reason: str,
    new_transform: str | None = None,
) -> dict:
    """Build a plain dict representation of a proposed field edit.

    Convenience function used in tests and scripts to construct edit payloads without
    importing ``EditIntent`` directly.

    Args:
        run_id: The pipeline run the edit applies to.
        field_id: Primary key of the ``FieldMapping`` row to update.
        new_target_path: Replacement target schema field name.
        reason: Human-readable explanation of the proposed change.
        new_transform: Replacement transform name, or ``None`` to keep unchanged.

    Returns:
        Plain dict matching the ``EditIntent`` schema.
    """
    return {
        "run_id": run_id,
        "field_id": field_id,
        "new_target_path": new_target_path,
        "new_transform": new_transform,
        "reason": reason,
    }
