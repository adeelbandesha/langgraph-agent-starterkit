import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.errors import AgentExecutionError
from src.state import AgentNode, CodeArtifact, PipelineState, QAReport, Specification
from src.utils.llm import invoke_structured

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a senior Python engineer. Implement the specification as one complete, runnable \
Python 3.11+ module.

- Use strict type hints, small focused functions and descriptive names.
- Do not write comments that restate the code; add a docstring only where intent is not obvious.
- Use the logging module for diagnostics; reserve print for intended user-facing output.
- Raise specific exceptions with clear messages; never silently swallow errors.
- If the module is a program, expose main() behind an if __name__ == "__main__" guard.
- Prefer the standard library unless the specification says otherwise.
- When QA feedback is present, fix every listed issue while keeping working behaviour intact.

Always return the entire file, never a diff or a partial snippet."""


def _build_request(
    specification: Specification,
    previous: CodeArtifact | None,
    report: QAReport | None,
) -> str:
    sections = [f"## Specification\n\n{specification.to_markdown()}"]
    if previous is not None and report is not None:
        sections.append(
            f"## Previous Implementation ({previous.filename})\n\n```python\n{previous.code}\n```"
        )
        sections.append(f"## QA Feedback To Address\n\n{report.to_markdown()}")
    return "\n\n".join(sections)


def build_implementer(llm: BaseChatModel) -> AgentNode:
    def implementer(state: PipelineState) -> PipelineState:
        specification = state.get("specification")
        if specification is None:
            raise AgentExecutionError("implementer", "no specification in state")

        iteration = state.get("iteration", 0) + 1
        logger.info("Writing implementation, iteration %d", iteration)
        request = _build_request(specification, state.get("code"), state.get("qa_report"))
        artifact = invoke_structured(
            llm,
            CodeArtifact,
            [SystemMessage(SYSTEM_PROMPT), HumanMessage(request)],
            agent="implementer",
        )
        logger.info("Produced %s (%d lines)", artifact.filename, artifact.line_count)
        logger.debug("Implementer notes: %s", artifact.notes or "none")
        return {"code": artifact, "iteration": iteration, "active_node": "implementer"}

    return implementer
