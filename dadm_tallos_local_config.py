from __future__ import annotations

import os
from pathlib import Path

from dadm_tallos_client import DADMTallosAPIError, DADMTallosClient

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"


def environment_name() -> str:
    return (os.getenv("ENVIRONMENT", "development") or "development").strip().lower()


def local_token_management_enabled() -> bool:
    return environment_name() not in {"production", "prod"}


def token_source() -> str:
    """Describe where the active token is managed without exposing its value."""
    active = os.getenv("TALLOS_API_TOKEN", "").strip()
    if not active:
        return "not_configured"
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or not stripped.startswith("TALLOS_API_TOKEN="):
                continue
            raw = stripped.split("=", 1)[1].strip()
            if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"\"", "'"}:
                raw = raw[1:-1]
            raw = raw.replace('\\"', '\"').replace('\\\\', '\\')
            if raw == active:
                return "local_env_file"
            return "server_environment"
    return "server_environment"


def _validate_token_text(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        raise ValueError("Informe o token TALLOS.")
    if len(token) < 12:
        raise ValueError("O token informado parece incompleto.")
    if len(token) > 4096:
        raise ValueError("O token informado é maior que o limite aceito.")
    if "\n" in token or "\r" in token:
        raise ValueError("O token não pode conter quebra de linha.")
    return token


def _dotenv_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def persist_local_token(value: str) -> None:
    if not local_token_management_enabled():
        raise PermissionError("A configuração de token pela interface é desativada em produção.")
    token = _validate_token_text(value)
    original = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    lines = original.splitlines()
    replacement = f"TALLOS_API_TOKEN={_dotenv_quote(token)}"
    output: list[str] = []
    replaced = False
    for line in lines:
        if line.lstrip().startswith("TALLOS_API_TOKEN="):
            if not replaced:
                output.append(replacement)
                replaced = True
            continue
        output.append(line)
    if not replaced:
        if output and output[-1].strip():
            output.append("")
        output.extend(["# DADM / TALLOS - configuração local", replacement])
    ENV_FILE.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    # dotenv is loaded with override=False. Updating the process environment makes
    # the new token usable immediately without restarting Uvicorn.
    os.environ["TALLOS_API_TOKEN"] = token


def clear_local_token() -> None:
    if not local_token_management_enabled():
        raise PermissionError("A configuração de token pela interface é desativada em produção.")
    if ENV_FILE.exists():
        lines = [line for line in ENV_FILE.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("TALLOS_API_TOKEN=")]
        ENV_FILE.write_text("\n".join(lines).rstrip() + ("\n" if lines else ""), encoding="utf-8")
    os.environ.pop("TALLOS_API_TOKEN", None)


def test_connection(token: str | None = None) -> dict:
    candidate = _validate_token_text(token) if token is not None and str(token).strip() else None
    client = DADMTallosClient(token=candidate)
    try:
        return client.test_connection()
    except DADMTallosAPIError:
        raise
