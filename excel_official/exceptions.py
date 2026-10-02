from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpecValidationIssue:
    code: str
    path: str
    message: str
    severity: str = "ERROR"

    def __str__(self) -> str:
        location = f" [{self.path}]" if self.path else ""
        return f"{self.severity} {self.code}{location}: {self.message}"


class WorkbookSpecValidationError(ValueError):
    def __init__(self, issues: tuple[SpecValidationIssue, ...] | list[SpecValidationIssue]):
        self.issues = tuple(issues)
        message = "WorkbookSpec invalido:\n" + "\n".join(f"- {issue}" for issue in self.issues)
        super().__init__(message)
