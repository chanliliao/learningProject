from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from app.config import get_settings


def _model(mode: str | None = None):
    s = get_settings()
    if (mode or s.llm_mode) == "test":
        return TestModel()
    return OpenAIModel(
        s.openrouter_model,
        provider=OpenAIProvider(base_url=s.openrouter_base_url, api_key=s.openrouter_api_key),
    )


async def ping_llm(mode: str | None = None) -> str:
    agent = Agent(_model(mode), output_type=str, system_prompt="Reply with a short greeting.")
    result = await agent.run("Say hello in five words or fewer.")
    return result.output
