from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from academic_excel_cutover import build_cutover_manifest, write_cutover_manifest
from release_info import APP_VERSION


def _get(url: str, *, cookie: str | None = None, timeout: float = 180.0) -> tuple[int, object, bytes]:
    headers = {"User-Agent": "Data-UNIVC-Academic-Excel-Prepare/1"}
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body[:500]!r}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture fresh DTNH+DCS production parity from the authenticated Reitoria endpoint and build the cutover gate."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cookie-env", default="DATA_UNIVC_REITORIA_COOKIE")
    parser.add_argument("--output-dir", type=Path, default=Path("academic_cutover_evidence"))
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    args = parser.parse_args()

    cookie = os.getenv(args.cookie_env, "").strip()
    if not cookie:
        raise SystemExit(f"Missing Reitoria session cookie in environment variable {args.cookie_env}.")

    base = args.base_url.rstrip("/")
    status, _headers, raw = _get(f"{base}/api/health/ready", timeout=args.timeout)
    if status != 200:
        raise SystemExit(f"Health readiness returned HTTP {status}.")
    health = json.loads(raw.decode("utf-8"))
    if not health.get("ok"):
        raise SystemExit(f"Health readiness is not OK: {health!r}")
    if str(health.get("version") or "") != APP_VERSION:
        raise SystemExit(f"Server version {health.get('version')!r} does not match local release {APP_VERSION}.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for code in ("DTNH", "DCS"):
        url = f"{base}/api/admin/excel-official/academic/parity?{urllib.parse.urlencode({'diretoria': code})}"
        status, headers, raw = _get(url, cookie=cookie, timeout=args.timeout)
        if status != 200:
            raise SystemExit(f"{code} parity endpoint returned HTTP {status}.")
        payload = json.loads(raw.decode("utf-8"))
        if str(payload.get("directorate") or "").upper() != code:
            raise SystemExit(f"{code} parity endpoint returned the wrong directorate.")
        path = args.output_dir / f"academic_parity_{code.lower()}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths[code] = path
        print(f"{code}: {payload.get('summary', {}).get('cutover_status', 'UNKNOWN')} -> {path}")
        header_status = str(headers.get("X-Data-UNIVC-Parity-Status") or "").strip()
        if header_status and header_status != str(payload.get("summary", {}).get("cutover_status") or ""):
            raise SystemExit(f"{code} parity status header/body mismatch.")

    manifest = build_cutover_manifest(
        dtnh_report_path=paths["DTNH"],
        dcs_report_path=paths["DCS"],
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


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
