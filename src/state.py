import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Literal, Required, TypedDict

from pydantic import BaseModel, Field, field_validator

AgentName = Literal["analyst", "implementer", "qa"]

DEFAULT_FILENAME = "solution.py"
SAFE_FILENAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\.py")


def _markdown_list(heading: str, items: list[str], numbered: bool = False) -> str:
    if not items:
        return ""
    lines = (f"{index}. {item}" if numbered else f"- {item}" for index, item in enumerate(items, 1))
    return f"## {heading}\n\n" + "\n".join(lines)


class Specification(BaseModel):
    title: str = Field(description="Short name of the feature.")
    summary: str = Field(description="One paragraph describing what will be built and for whom.")
    functional_requirements: list[str] = Field(
        description="Concrete, testable behaviours the implementation must exhibit."
    )
    interface: str = Field(
        description="Public interface: CLI usage, function signatures or class APIs, as Markdown."
    )
    edge_cases: list[str] = Field(
        default_factory=list, description="Invalid inputs and boundary conditions to handle."
    )
    acceptance_criteria: list[str] = Field(
        description="Verifiable conditions QA will use to approve the implementation."
    )
    assumptions: list[str] = Field(
        default_factory=list, description="Defaults chosen where the request was ambiguous."
    )

    def to_markdown(self) -> str:
        sections = [
            f"# {self.title}",
            self.summary,
            _markdown_list("Functional Requirements", self.functional_requirements, numbered=True),
            f"## Interface\n\n{self.interface}",
            _markdown_list("Edge Cases", self.edge_cases),
            _markdown_list("Acceptance Criteria", self.acceptance_criteria, numbered=True),
            _markdown_list("Assumptions", self.assumptions),
        ]
        return "\n\n".join(section for section in sections if section)


class CodeArtifact(BaseModel):
    filename: str = Field(
        description="Module filename in snake_case ending in .py, e.g. calculator.py."
    )
    code: str = Field(description="The complete, runnable Python source of the module.")
    notes: str = Field(
        default="", description="Key design decisions, or what changed in response to QA feedback."
    )

    @field_validator("filename")
    @classmethod
    def _sanitize_filename(cls, value: str) -> str:
        # The filename comes from the model and is later written to disk, so never trust its path.
        name = PurePosixPath(value.strip().replace("\\", "/")).name
        return name if SAFE_FILENAME.fullmatch(name) else DEFAULT_FILENAME

    @property
    def line_count(self) -> int:
        return len(self.code.splitlines())


class ValidationCheck(BaseModel):
    name: str = Field(description="Short identifier of the check.")
    scenario: str = Field(description="The input or action the check exercises.")
    expected: str = Field(description="The behaviour the specification requires.")
    passed: bool = Field(description="Whether tracing the code shows the expected behaviour.")
    details: str = Field(default="", description="Observed behaviour when the check fails.")


class QAReport(BaseModel):
    approved: bool = Field(
        description="True only if every acceptance criterion is met and every check passes."
    )
    summary: str = Field(description="Two or three sentences on overall quality and the verdict.")
    checks: list[ValidationCheck] = Field(default_factory=list)
    issues: list[str] = Field(
        default_factory=list,
        description="Concrete, actionable defects for the implementer. Empty when approved.",
    )
    test_script: str = Field(
        default="",
        description=(
            "A standalone Python script that runs every check against the module using plain "
            "assert statements and exits non-zero on the first failure. Use real line breaks, "
            "not \\n escape sequences."
        ),
    )

    @property
    def passed(self) -> bool:
        return self.approved and all(check.passed for check in self.checks)

    @property
    def passed_check_count(self) -> int:
        return sum(check.passed for check in self.checks)

    def to_markdown(self, include_passed_checks: bool = True) -> str:
        verdict = "APPROVED" if self.passed else "CHANGES REQUESTED"
        checks = [check for check in self.checks if include_passed_checks or not check.passed]
        check_lines = [
            f"- [{'x' if check.passed else ' '}] **{check.name}**: {check.scenario} "
            f"-> expected {check.expected}"
            + (f" (observed: {check.details})" if check.details else "")
            for check in checks
        ]
        sections = [
            f"# QA Report: {verdict}",
            self.summary,
            "## Checks\n\n" + "\n".join(check_lines) if check_lines else "",
            _markdown_list("Issues", self.issues, numbered=True),
        ]
        return "\n\n".join(section for section in sections if section)


class PipelineState(TypedDict, total=False):
    prompt: Required[str]
    specification: Specification
    code: CodeArtifact
    qa_report: QAReport
    active_node: AgentName
    iteration: int


AgentNode = Callable[[PipelineState], PipelineState]
