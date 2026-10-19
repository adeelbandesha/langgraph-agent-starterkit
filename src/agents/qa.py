import ast
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import TARGET_PYTHON
from src.errors import AgentExecutionError
from src.state import AgentNode, CodeArtifact, PipelineState, QAReport, Specification
from src.utils.executor import run_test_script
from src.utils.llm import invoke_structured

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""\
You are a meticulous QA engineer reviewing a module that will run on Python {TARGET_PYTHON}.

1. Derive 5 to 10 checks. Cover every acceptance criterion first, then add checks for inputs \
the criteria do not mention: malformed or unsupported input, boundary values, and inputs large \
enough to make the program hang or exhaust memory.
2. For each check, trace the code by hand with the given scenario and record whether the \
observed behaviour matches the expected behaviour. Describe what actually happens when it fails.
3. Treat any use of an API that is deprecated or removed in Python {TARGET_PYTHON} as a defect, \
even on a rarely reached code path.
4. Write test_script: a standalone script that runs every check and exits non-zero on the first \
failure. Import the module by its filename stem to test functions, and use \
subprocess.run([sys.executable, "<filename>", ...], capture_output=True, text=True, timeout=10) \
to test command-line behaviour. Use plain assert statements and the standard library only. \
Assert exact output text only where the specification states it word for word; otherwise \
assert exit codes, the output stream and the key values.
5. Approve only if every acceptance criterion is met and every check passes.
6. List each defect as a concrete, actionable issue naming the function and the fix. \
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


def _verify_by_execution(report: QAReport, artifact: CodeArtifact) -> QAReport:
    problem = find_syntax_error(report.test_script) if report.test_script.strip() else "none returned"
    if problem is not None:
        # A broken test script is QA's fault, so it must not count against the implementer.
        logger.warning("QA test script is unusable (%s); keeping the review-only verdict", problem)
        return report.model_copy(update={"test_script": ""})

    result = run_test_script(artifact, report.test_script)
    logger.info("Executed QA test script: %s", "passed" if result.passed else "failed")
    if result.passed:
        return report
    return report.model_copy(
        update={
            "approved": False,
            "issues": [
                *report.issues,
                f"Running the QA test script failed. Output:\n{result.output.strip()}",
            ],
        }
    )


def build_qa(llm: BaseChatModel, execute_checks: bool = False) -> AgentNode:
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
            if execute_checks:
                report = _verify_by_execution(report, artifact)

        logger.info(
            "QA verdict: %s (%d/%d checks passed, %d issues)",
            "approved" if report.passed else "changes requested",
            report.passed_check_count,
            len(report.checks),
            len(report.issues),
        )
        return {"qa_report": report, "active_node": "qa"}

    return qa
