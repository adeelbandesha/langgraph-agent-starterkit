import os
import time

import pytest

from src.main import build_graph
from src.state import CodeArtifact, QAReport
from src.utils.executor import run_test_script
from tests.test_pipeline import APPROVAL, FIXED_CODE, SPECIFICATION, ScriptedModel

ADDER = CodeArtifact(filename="adder.py", code="def add(a: int, b: int) -> int:\n    return a - b\n")
CHECK_ADDER = "import adder\nassert adder.add(2, 3) == 5, adder.add(2, 3)\n"


def test_passing_script_passes() -> None:
    assert run_test_script(FIXED_CODE, CHECK_ADDER).passed


def test_failing_script_reports_the_real_output() -> None:
    result = run_test_script(ADDER, CHECK_ADDER)

    assert not result.passed
    assert "AssertionError: -1" in result.output


def test_hanging_code_is_killed_including_child_processes() -> None:
    script = (
        "import subprocess, sys\n"
        "subprocess.run([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    )
    started = time.monotonic()
    result = run_test_script(ADDER, script, timeout=1)

    assert not result.passed
    assert "Timed out" in result.output
    assert time.monotonic() - started < 10


def test_generated_code_cannot_read_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret-value")
    script = "import os\nassert 'OPENAI_API_KEY' not in os.environ\n"

    assert run_test_script(ADDER, script).passed
    assert os.environ["OPENAI_API_KEY"] == "secret-value"


def test_execution_overrides_a_mistaken_approval() -> None:
    approved_but_wrong = APPROVAL.model_copy(update={"test_script": CHECK_ADDER})
    model = ScriptedModel(SPECIFICATION, ADDER, approved_but_wrong, FIXED_CODE, approved_but_wrong)

    state = build_graph(model, 3, execute_checks=True).invoke(  # type: ignore[arg-type]
        {"prompt": "add numbers", "iteration": 0}
    )
    report: QAReport = state["qa_report"]

    assert state["iteration"] == 2
    assert state["code"] == FIXED_CODE
    assert report.passed


def test_unparseable_test_script_falls_back_to_review_verdict() -> None:
    escaped_script = APPROVAL.model_copy(update={"test_script": "import adder\\nassert False"})
    model = ScriptedModel(SPECIFICATION, FIXED_CODE, escaped_script)

    state = build_graph(model, 3, execute_checks=True).invoke(  # type: ignore[arg-type]
        {"prompt": "add numbers", "iteration": 0}
    )

    assert state["iteration"] == 1
    assert state["qa_report"].passed
    assert state["qa_report"].test_script == ""
