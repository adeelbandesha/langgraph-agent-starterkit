import logging
from collections.abc import Sequence
from typing import Any, TypeVar

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.config import Settings
from src.errors import AgentExecutionError

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def create_chat_model(settings: Settings) -> BaseChatModel:
    options: dict[str, Any] = {
        "model": settings.resolved_model,
        "max_tokens": settings.max_tokens,
        "max_retries": settings.max_retries,
    }
    # Only send temperature when configured: some models reject sampling parameters outright.
    if settings.temperature is not None:
        options["temperature"] = settings.temperature

    logger.debug("Creating %s chat model %s", settings.provider, settings.resolved_model)
    if settings.provider == "anthropic":
        return ChatAnthropic(**options)
    return ChatOpenAI(**options)


def invoke_structured(
    llm: BaseChatModel,
    schema: type[SchemaT],
    messages: Sequence[BaseMessage],
    agent: str,
) -> SchemaT:
    """Call the model with a Pydantic output schema, raising AgentExecutionError on any failure."""
    try:
        result = llm.with_structured_output(schema).invoke(list(messages))
    except Exception as exc:
        raise AgentExecutionError(agent, f"LLM call failed: {exc}") from exc

    if not isinstance(result, schema):
        raise AgentExecutionError(agent, f"model did not return a valid {schema.__name__}")
    return result
