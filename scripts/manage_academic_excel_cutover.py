from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from academic_excel_finalization import build_academic_finalization_report, write_academic_finalization_report
from academic_excel_cutover import (
    ENABLE_CONFIRMATION,
    activate_cutover,
    build_cutover_manifest,
    read_env_flag,
    rollback_cutover,
    write_cutover_manifest,
)


def _reports(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dtnh-report", type=Path, required=True)
    parser.add_argument("--dcs-report", type=Path, required=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled Academic Excel Official production cutover utility.")
    sub = parser.add_subparsers(dest="command", required=True)

    gate = sub.add_parser("gate", help="Validate fresh DTNH+DCS READY production reports and write a cutover manifest.")
    _reports(gate)
    gate.add_argument("--output-dir", type=Path, default=Path("cutover_output"))
    gate.add_argument("--max-age-hours", type=float, default=24.0)

    activate = sub.add_parser("activate", help="Atomically enable the production env flag after revalidating the manifest/reports.")
    _reports(activate)
    activate.add_argument("--manifest", type=Path, required=True)
    activate.add_argument("--env-file", type=Path, default=Path(".env.production"))
    activate.add_argument("--confirm", required=True, help=f"Must equal {ENABLE_CONFIRMATION}")

    rollback = sub.add_parser("rollback", help="Atomically disable the Excel Official flag. Does not require readiness evidence.")
    rollback.add_argument("--env-file", type=Path, default=Path(".env.production"))

    status = sub.add_parser("status", help="Show the persisted cutover flag in an env file.")
    status.add_argument("--env-file", type=Path, default=Path(".env.production"))

    finalize = sub.add_parser("finalize", help="Produce the final DTNH+DCS completion record after authenticated post-cutover smokes.")
    _reports(finalize)
    finalize.add_argument("--manifest", type=Path, required=True)
    finalize.add_argument("--dtnh-smoke", type=Path, required=True)
    finalize.add_argument("--dcs-smoke", type=Path, required=True)
    finalize.add_argument("--output-dir", type=Path, default=Path("cutover_output"))

    args = parser.parse_args()

    if args.command == "gate":
        manifest = build_cutover_manifest(
            dtnh_report_path=args.dtnh_report,
            dcs_report_path=args.dcs_report,
            max_age_hours=args.max_age_hours,
        )
        json_path, md_path = write_cutover_manifest(manifest, args.output_dir)
        print(f"Cutover gate: {manifest.status}")
        print(f"Manifest: {json_path}")
        print(f"Report: {md_path}")
        for issue in manifest.issues:
            scope = f" [{issue.directorate}]" if issue.directorate else ""
            print(f"- {issue.code}{scope}: {issue.message}")
        return 0 if manifest.ready else 2

    if args.command == "activate":
        manifest, backup, changed = activate_cutover(
            manifest_path=args.manifest,
            dtnh_report_path=args.dtnh_report,
            dcs_report_path=args.dcs_report,
            env_path=args.env_file,
            confirmation=args.confirm,
        )
        print(f"Cutover evidence: {manifest.status} ({manifest.manifest_id})")
        print(f"{args.env_file}: ACADEMIC_EXCEL_OFFICIAL_ENABLED=true")
        if backup:
            print(f"Backup: {backup}")
        print("Changed: " + ("yes" if changed else "no (already enabled)"))
        print("Restart required: docker compose -f docker-compose.production.yml up -d --force-recreate app")
        return 0

    if args.command == "rollback":
        backup, changed = rollback_cutover(env_path=args.env_file)
        print(f"{args.env_file}: ACADEMIC_EXCEL_OFFICIAL_ENABLED=false")
        if backup:
            print(f"Backup: {backup}")
        print("Changed: " + ("yes" if changed else "no (already disabled)"))
        print("Restart required: docker compose -f docker-compose.production.yml up -d --force-recreate app")
        return 0

    if args.command == "finalize":
        report = build_academic_finalization_report(
            manifest_path=args.manifest,
            dtnh_report_path=args.dtnh_report,
            dcs_report_path=args.dcs_report,
            dtnh_smoke_path=args.dtnh_smoke,
            dcs_smoke_path=args.dcs_smoke,
        )
        json_path, md_path = write_academic_finalization_report(report, args.output_dir)
        print(f"Academic finalization: {report.status}")
        print(f"JSON: {json_path}")
        print(f"Report: {md_path}")
        for issue in report.issues:
            scope = f" [{issue.directorate}]" if issue.directorate else ""
            print(f"- {issue.code}{scope}: {issue.message}")
        return 0 if report.complete else 2

    enabled = read_env_flag(args.env_file)
    print(f"{args.env_file}: ACADEMIC_EXCEL_OFFICIAL_ENABLED={'true' if enabled else 'false'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
