import logging

from rich.console import Console
from rich.logging import RichHandler

# Logs and the progress spinner share stderr so they never tear each other, and stdout stays pipeable.
stderr_console = Console(stderr=True)

NOISY_LOGGERS = ("httpx", "httpcore", "anthropic", "openai", "urllib3")


def configure_logging(level: str | int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(name)s: %(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=stderr_console,
                show_path=False,
                rich_tracebacks=True,
                markup=False,
            )
        ],
        force=True,
    )
    verbose = logging.getLogger().isEnabledFor(logging.DEBUG)
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO if verbose else logging.WARNING)
