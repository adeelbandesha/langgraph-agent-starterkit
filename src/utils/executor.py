import logging
import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.state import CodeArtifact

logger = logging.getLogger(__name__)

EXECUTION_TIMEOUT_SECONDS = 30.0
OUTPUT_TAIL_CHARACTERS = 2000

# Generated code must never see API keys, so the child process gets only what Python needs to start.
INHERITED_ENVIRONMENT_VARIABLES = ("PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT")


@dataclass(frozen=True)
class ExecutionResult:
    passed: bool
    output: str


def qa_script_filename(artifact: CodeArtifact) -> str:
    return f"test_{artifact.filename}"


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGKILL)
    else:
        process.kill()


def run_test_script(
    artifact: CodeArtifact,
    test_script: str,
    timeout: float = EXECUTION_TIMEOUT_SECONDS,
) -> ExecutionResult:
    """Run a QA test script against the module in a throwaway directory, with a timeout and no secrets."""
    environment = {
        name: value
        for name in INHERITED_ENVIRONMENT_VARIABLES
        if (value := os.environ.get(name)) is not None
    }
    with tempfile.TemporaryDirectory(prefix="agentkit-qa-") as workdir:
        Path(workdir, artifact.filename).write_text(artifact.code, encoding="utf-8")
        Path(workdir, qa_script_filename(artifact)).write_text(test_script, encoding="utf-8")
        logger.debug("Executing QA checks in %s", workdir)

        # A new session lets a timeout kill grandchildren too, e.g. a CLI the test script launched.
        process = subprocess.Popen(
            [sys.executable, "-s", qa_script_filename(artifact)],
            cwd=workdir,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_process_tree(process)
            process.communicate()
            return ExecutionResult(
                passed=False,
                output=f"Timed out after {timeout:.0f}s: the code hangs or loops on one of the checks.",
            )

    return ExecutionResult(passed=process.returncode == 0, output=output[-OUTPUT_TAIL_CHARACTERS:])
