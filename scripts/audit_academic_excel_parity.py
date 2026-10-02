from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from academic_excel_parity import (
    AcademicCutoverReadiness,
    audit_academic_payload_parity,
    write_parity_report,
)


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object payload")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit DTNH/DCS Academic Excel parity from authorized snapshot JSON payloads."
    )
    parser.add_argument("snapshots", nargs="+", type=Path, help="One or more Academic interactive payload JSON files")
    parser.add_argument("--output-dir", type=Path, default=Path("parity_output"))
    parser.add_argument(
        "--source-kind",
        choices=("fixture", "local", "production"),
        default="local",
        help="Use production only for snapshots captured from the live authorized repository.",
    )
    parser.add_argument("--semantic-only", action="store_true", help="Skip legacy/new workbook build evidence")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for snapshot in args.snapshots:
        payload = _load(snapshot)
        report = audit_academic_payload_parity(
            payload,
            source_kind=args.source_kind,
            build_workbooks=not args.semantic_only,
        )
        reports.append(report)
        json_path, md_path = write_parity_report(report, args.output_dir)
        print(f"{report.directorate}: {report.cutover_status} -> {json_path} / {md_path}")

    readiness = AcademicCutoverReadiness(tuple(reports))
    readiness_path = args.output_dir / "academic_cutover_readiness.md"
    readiness_path.write_text(readiness.to_markdown(), encoding="utf-8")
    print(f"Overall: {readiness.status} -> {readiness_path}")
    return 0 if readiness.status != "BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
