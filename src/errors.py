class AgentKitError(Exception):
    """Base class for every error the pipeline raises deliberately."""


class ConfigurationError(AgentKitError):
    """The environment or .env file is missing or holds an invalid value."""


class AgentExecutionError(AgentKitError):
    """An agent could not produce a valid output."""

    def __init__(self, agent: str, message: str) -> None:
        super().__init__(f"{agent}: {message}")
        self.agent = agent


class OutputWriteError(AgentKitError):
    """Generated artifacts could not be written to disk."""
