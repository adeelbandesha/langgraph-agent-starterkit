import logging
from pathlib import Path
from typing import Annotated, cast

import typer
from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from src.agents import build_analyst, build_implementer, build_qa
from src.config import load_settings
from src.errors import AgentExecutionError, AgentKitError, OutputWriteError
from src.state import PipelineState
from src.utils.executor import qa_script_filename
from src.utils.llm import create_chat_model
from src.utils.logger import configure_logging, stderr_console

logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False, no_args_is_help=True, rich_markup_mode="rich")
stdout_console = Console()


def build_graph(
    llm: BaseChatModel, max_iterations: int, execute_checks: bool = False
) -> CompiledStateGraph:
    """Wire analyst -> implementer -> qa, looping back to the implementer until QA approves."""

    def route_after_qa(state: PipelineState) -> str:
        if state["qa_report"].passed:
            return END
        if state["iteration"] >= max_iterations:
            logger.warning("QA still rejects the code after %d iterations; stopping", max_iterations)
            return END
        return "implementer"

    graph = StateGraph(PipelineState)
    graph.add_node("analyst", build_analyst(llm))
    graph.add_node("implementer", build_implementer(llm))
    graph.add_node("qa", build_qa(llm, execute_checks))
    graph.add_edge(START, "analyst")
    graph.add_edge("analyst", "implementer")
    graph.add_edge("implementer", "qa")
    graph.add_conditional_edges("qa", route_after_qa, ["implementer", END])
    return graph.compile()


def describe_progress(state: PipelineState) -> str:
    match state.get("active_node"):
        case None:
            return "Analyst is drafting the specification..."
        case "analyst":
            return "Implementer is writing the code..."
        case "implementer":
            return f"QA is reviewing iteration {state['iteration']}..."
        case _:
            return "Implementer is addressing QA feedback..."


def execute_pipeline(graph: CompiledStateGraph, request: str, max_iterations: int) -> PipelineState:
    """Stream the graph to completion, falling back to the last reviewed round if a later LLM call fails."""
    state: PipelineState = {"prompt": request, "iteration": 0}
    last_reviewed: PipelineState | None = None
    # Each QA round costs two graph steps; leave headroom so long loops never hit the default limit.
    config = {"recursion_limit": 2 * max_iterations + 5}

    with stderr_console.status(describe_progress(state), spinner="dots") as status:
        try:
            for snapshot in graph.stream(state, config=config, stream_mode="values"):
                state = cast(PipelineState, snapshot)
                if state.get("active_node") == "qa":
                    last_reviewed = state
                status.update(describe_progress(state))
        except AgentExecutionError as exc:
            if last_reviewed is None:
                raise
            logger.error("%s", exc)
            logger.warning(
                "Keeping the results of iteration %d, the last one QA reviewed",
                last_reviewed["iteration"],
            )
            return last_reviewed
    return state


def render_results(state: PipelineState, execute_checks: bool) -> None:
    specification, artifact, report = state["specification"], state["code"], state["qa_report"]

    stdout_console.print(
        Panel(Markdown(specification.to_markdown()), title="Specification", border_style="cyan")
    )
    stdout_console.print(
        Panel(
            Syntax(artifact.code, "python", line_numbers=True, word_wrap=True),
            title=escape(artifact.filename),
            border_style="green",
        )
    )

    table = Table(title=f"QA Validation - iteration {state['iteration']}", expand=True)
    table.add_column("Check", style="bold")
    table.add_column("Scenario")
    table.add_column("Expected")
    table.add_column("Result", justify="center")
    for check in report.checks:
        table.add_row(
            escape(check.name),
            escape(check.scenario),
            escape(check.expected),
            "[green]PASS[/]" if check.passed else "[red]FAIL[/]",
        )
    if report.checks:
        stdout_console.print(table)

    verdict_style = "green" if report.passed else "red"
    verdict = "APPROVED" if report.passed else "CHANGES REQUESTED"
    executed = execute_checks and bool(report.test_script.strip())
    method = "test script executed" if executed else "review only, not executed"
    body = escape(report.summary)
    if report.issues:
        body += "\n\n" + "\n".join(f"- {escape(issue)}" for issue in report.issues)
    stdout_console.print(
        Panel(body, title=f"QA Verdict: {verdict} ({method})", border_style=verdict_style)
    )


def save_artifacts(state: PipelineState, directory: Path) -> list[Path]:
    artifact = state["code"]
    files = {
        directory / "SPEC.md": state["specification"].to_markdown(),
        directory / artifact.filename: artifact.code,
        directory / "QA_REPORT.md": state["qa_report"].to_markdown(),
    }
    if state["qa_report"].test_script.strip():
        files[directory / qa_script_filename(artifact)] = state["qa_report"].test_script
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for path, content in files.items():
            path.write_text(content.rstrip() + "\n", encoding="utf-8")
    except OSError as exc:
        raise OutputWriteError(f"could not write artifacts to {directory}: {exc}") from exc
    return list(files)


@app.callback()
def cli() -> None:
    """Multi-agent engineering pipeline: [cyan]analyst[/] -> [green]implementer[/] -> [magenta]QA[/]."""


@app.command()
def run(
    request: Annotated[str, typer.Argument(help="The feature request, in plain English.")],
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-o",
            file_okay=False,
            help="Write SPEC.md, the generated module, its QA test script and QA_REPORT.md to this directory.",
        ),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option(
            "--execute",
            "-x",
            help="Run QA's test script against the generated code. Runs model-written code locally.",
        ),
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable debug logging.")
    ] = False,
) -> None:
    """Turn a feature request into a specification, an implementation and a QA verdict."""
    if not request.strip():
        raise typer.BadParameter("the feature request cannot be empty", param_hint="REQUEST")

    try:
        settings = load_settings()
        configure_logging(logging.DEBUG if verbose else settings.log_level)
        logger.info("Using %s model %s", settings.provider, settings.resolved_model)
        graph = build_graph(create_chat_model(settings), settings.max_qa_iterations, execute)
        state = execute_pipeline(graph, request.strip(), settings.max_qa_iterations)
        render_results(state, execute)
        if output_dir is not None:
            for path in save_artifacts(state, output_dir):
                stdout_console.print(f"[dim]Saved[/] {escape(str(path))}")
    except AgentKitError as exc:
        stderr_console.print(f"[bold red]Error:[/] {escape(str(exc))}")
        raise typer.Exit(code=1) from exc

    if not state["qa_report"].passed:
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
