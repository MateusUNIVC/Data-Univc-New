from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(label: str, command: list[str]) -> None:
    print(f"\n== {label} ==")
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    py_files = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*.py") if ".venv" not in path.parts]
    run("Python compile", [sys.executable, "-m", "py_compile", *py_files])

    js_files = sorted((ROOT / "static" / "js").glob("dpe*.js"))
    for path in js_files:
        run(f"JavaScript syntax: {path.name}", ["node", "--check", str(path.relative_to(ROOT))])

    run("Pytest", [sys.executable, "-m", "pytest", "-q"])

    forbidden_files = [ROOT / "dpe_excel_parser.py", ROOT / "dpe_excel_builder.py", ROOT / "static" / "js" / "dpe_finance.js"]
    leftovers = [str(path.relative_to(ROOT)) for path in forbidden_files if path.exists()]
    if leftovers:
        raise SystemExit("Legacy DPE files unexpectedly present: " + ", ".join(leftovers))

    active_paths = [ROOT / "templates" / "dpe.html", *sorted((ROOT / "static" / "js").glob("dpe*.js"))]
    active_text = "\n".join(path.read_text(encoding="utf-8") for path in active_paths)
    forbidden_tokens = ["DPE-01", "DPE-02", "DPE-03", "Histórico e legado", "Historico e legado"]
    found = [token for token in forbidden_tokens if token in active_text]
    if found:
        raise SystemExit("Legacy DPE frontend tokens found: " + ", ".join(found))

    print("\nRelease checks OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
