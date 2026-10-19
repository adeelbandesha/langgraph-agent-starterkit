import ast
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.errors import AgentExecutionError
from src.state import AgentNode, CodeArtifact, PipelineState, QAReport, Specification
from src.utils.llm import invoke_structured

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a meticulous QA engineer. You cannot execute code, so validate it by tracing its \
execution by hand.

1. Derive 4 to 8 checks from the acceptance criteria and edge cases in the specification.
2. For each check, walk through the code with the given scenario and record whether the \
observed behaviour matches the expected behaviour. Describe what actually happens when it fails.
3. Approve only if every acceptance criterion is met and every check passes.
4. List each defect as a concrete, actionable issue naming the function and the fix. \
Do not raise style preferences as issues."""


def find_syntax_error(source: str) -> str | None:
    try:
        ast.parse(source)
    except SyntaxError as exc:
        return f"SyntaxError on line {exc.lineno}: {exc.msg}"
    return None


def _syntax_failure_report(error: str) -> QAReport:
    return QAReport(
        approved=False,
        summary="The module does not parse, so behavioural review was skipped.",
        issues=[f"{error}. Return the complete file as valid Python."],
    )


def _build_request(specification: Specification, artifact: CodeArtifact) -> str:
    return (
        f"## Specification\n\n{specification.to_markdown()}\n\n"
        f"## Implementation ({artifact.filename})\n\n```python\n{artifact.code}\n```"
    )


def build_qa(llm: BaseChatModel) -> AgentNode:
    def qa(state: PipelineState) -> PipelineState:
        specification = state.get("specification")
        artifact = state.get("code")
        if specification is None or artifact is None:
            raise AgentExecutionError("qa", "specification and code must both be present in state")

        syntax_error = find_syntax_error(artifact.code)
        if syntax_error is not None:
            logger.warning("Static check failed for %s: %s", artifact.filename, syntax_error)
            report = _syntax_failure_report(syntax_error)
        else:
            logger.info("Reviewing %s", artifact.filename)
            report = invoke_structured(
                llm,
                QAReport,
                [SystemMessage(SYSTEM_PROMPT), HumanMessage(_build_request(specification, artifact))],
                agent="qa",
            )

        logger.info(
            "QA verdict: %s (%d/%d checks passed, %d issues)",
            "approved" if report.passed else "changes requested",
            report.passed_check_count,
            len(report.checks),
            len(report.issues),
        )
        return {"qa_report": report, "active_node": "qa"}

    return qa
