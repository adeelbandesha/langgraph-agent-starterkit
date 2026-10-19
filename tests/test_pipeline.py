from collections import defaultdict, deque
from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from src.errors import AgentExecutionError
from src.main import build_graph
from src.state import CodeArtifact, QAReport, Specification, ValidationCheck

SPECIFICATION = Specification(
    title="Adder",
    summary="Adds two integers.",
    functional_requirements=["add(a, b) returns a + b"],
    interface="`add(a: int, b: int) -> int`",
    acceptance_criteria=["add(2, 3) == 5"],
)
BUGGY_CODE = CodeArtifact(filename="adder.py", code="def add(a: int, b: int) -> int:\n    return a - b\n")
FIXED_CODE = CodeArtifact(filename="adder.py", code="def add(a: int, b: int) -> int:\n    return a + b\n")
REJECTION = QAReport(
    approved=False,
    summary="Subtracts instead of adding.",
    checks=[ValidationCheck(name="sum", scenario="add(2, 3)", expected="5", passed=False)],
    issues=["add returns a - b; return a + b"],
)
APPROVAL = QAReport(
    approved=True,
    summary="Correct.",
    checks=[ValidationCheck(name="sum", scenario="add(2, 3)", expected="5", passed=True)],
)


class ScriptedModel:
    """Replays canned structured outputs per schema in place of a real chat model."""

    def __init__(self, *responses: BaseModel) -> None:
        self.queues: dict[type[BaseModel], deque[BaseModel]] = defaultdict(deque)
        for response in responses:
            self.queues[type(response)].append(response)

    def with_structured_output(self, schema: type[BaseModel]) -> RunnableLambda[Any, BaseModel]:
        return RunnableLambda(lambda _messages: self.queues[schema].popleft())


def run_graph(model: ScriptedModel, max_iterations: int = 3) -> dict[str, Any]:
    return build_graph(model, max_iterations).invoke({"prompt": "add numbers", "iteration": 0})  # type: ignore[arg-type]


def test_rejected_code_loops_back_until_qa_approves() -> None:
    state = run_graph(ScriptedModel(SPECIFICATION, BUGGY_CODE, REJECTION, FIXED_CODE, APPROVAL))

    assert state["iteration"] == 2
    assert state["code"] == FIXED_CODE
    assert state["qa_report"].passed
    assert state["active_node"] == "qa"


def test_pipeline_stops_at_iteration_limit() -> None:
    state = run_graph(ScriptedModel(SPECIFICATION, BUGGY_CODE, REJECTION), max_iterations=1)

    assert state["iteration"] == 1
    assert not state["qa_report"].passed


def test_syntax_error_is_rejected_without_calling_the_model() -> None:
    broken = CodeArtifact(filename="adder.py", code="def add(a, b)\n    return a + b\n")
    state = run_graph(ScriptedModel(SPECIFICATION, broken), max_iterations=1)

    assert "SyntaxError on line 1" in state["qa_report"].issues[0]


def test_approval_with_failing_check_does_not_pass() -> None:
    contradictory = REJECTION.model_copy(update={"approved": True})

    assert not contradictory.passed


def test_model_failure_is_wrapped_in_agent_error() -> None:
    with pytest.raises(AgentExecutionError, match="analyst"):
        run_graph(ScriptedModel())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("calculator.py", "calculator.py"),
        ("pkg/calculator.py", "calculator.py"),
        ("../../etc/passwd", "solution.py"),
        ("..\\evil.py", "evil.py"),
        ("notes.txt", "solution.py"),
    ],
)
def test_generated_filename_is_sanitized(raw: str, expected: str) -> None:
    assert CodeArtifact(filename=raw, code="").filename == expected
