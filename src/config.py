import os
from typing import Literal

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, Field, ValidationError

from src.errors import ConfigurationError

Provider = Literal["anthropic", "openai"]

DEFAULT_MODELS: dict[Provider, str] = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-4.1",
}

API_KEY_VARIABLES: dict[Provider, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}

ENVIRONMENT_VARIABLES: dict[str, str] = {
    "provider": "LLM_PROVIDER",
    "model": "LLM_MODEL",
    "temperature": "LLM_TEMPERATURE",
    "max_tokens": "LLM_MAX_TOKENS",
    "max_qa_iterations": "MAX_QA_ITERATIONS",
    "log_level": "LOG_LEVEL",
}


class Settings(BaseModel):
    provider: Provider = "anthropic"
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8192, gt=0)
    max_qa_iterations: int = Field(default=3, ge=1, le=10)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @property
    def resolved_model(self) -> str:
        return self.model or DEFAULT_MODELS[self.provider]


def load_settings() -> Settings:
    """Read settings from the environment and .env, failing fast on bad values or a missing API key."""
    load_dotenv(find_dotenv(usecwd=True))
    raw_values = {
        field: value
        for field, variable in ENVIRONMENT_VARIABLES.items()
        if (value := os.getenv(variable, "").strip())
    }
    try:
        settings = Settings.model_validate(raw_values)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid configuration in environment/.env:\n{exc}") from exc

    key_variable = API_KEY_VARIABLES[settings.provider]
    if not os.getenv(key_variable, "").strip():
        raise ConfigurationError(
            f"{key_variable} is not set. Copy .env.example to .env and add your key, "
            f"or switch LLM_PROVIDER."
        )
    return settings
