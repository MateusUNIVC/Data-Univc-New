from __future__ import annotations

from dataclasses import dataclass

from ..contract import QualitySeverity


@dataclass(frozen=True, slots=True)
class AuditFinding:
    code: str
    severity: QualitySeverity
    message: str
    sheet_name: str | None = None
    cell_reference: str | None = None


@dataclass(frozen=True, slots=True)
class AuditResult:
    findings: tuple[AuditFinding, ...] = ()
    checks_run: int = 0

    @property
    def blocking_findings(self) -> tuple[AuditFinding, ...]:
        return tuple(item for item in self.findings if item.severity is QualitySeverity.BLOCKING)

    @property
    def error_findings(self) -> tuple[AuditFinding, ...]:
        return tuple(item for item in self.findings if item.severity is QualitySeverity.ERROR)

    @property
    def warning_findings(self) -> tuple[AuditFinding, ...]:
        return tuple(item for item in self.findings if item.severity is QualitySeverity.WARNING)

    @property
    def release_allowed(self) -> bool:
        return not self.blocking_findings

    @property
    def valid(self) -> bool:
        return self.release_allowed


class WorkbookReleaseBlockedError(RuntimeError):
    def __init__(self, audit: AuditResult):
        self.audit = audit
        summary = "; ".join(f"{item.code}: {item.message}" for item in audit.blocking_findings)
        super().__init__(f"Excel Official release blocked: {summary or 'blocking audit finding'}")
