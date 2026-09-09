from __future__ import annotations

import os
import hmac
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv

from auth.test_accounts import account_for_email, local_test_auth_enabled, local_test_password

load_dotenv()


@dataclass(frozen=True)
class IdentityProviderError(Exception):
    status_code: int
    message: str

    def __str__(self) -> str:
        return self.message


def _config() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
    missing = []
    if not url:
        missing.append("SUPABASE_URL")
    if not key:
        missing.append("SUPABASE_PUBLISHABLE_KEY")
    if missing:
        raise IdentityProviderError(500, "Configuração do Supabase incompleta. Defina: " + ", ".join(missing) + ".")
    return url, key


def _message(response: httpx.Response, fallback: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        return fallback
    return (
        payload.get("msg")
        or payload.get("message")
        or payload.get("error_description")
        or payload.get("error")
        or fallback
    )


async def authenticate_password(email: str, password: str) -> dict:
    if local_test_auth_enabled():
        account = account_for_email(email)
        expected = local_test_password()
        if not account or not expected or not hmac.compare_digest(str(password or ""), expected):
            raise IdentityProviderError(401, "E-mail ou senha inválidos.")
        return {
            "user": {
                "id": account.user_id,
                "email": account.email,
                "user_metadata": {"name": account.name},
            },
            "provider": "LOCAL_TEST",
        }

    url, key = _config()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{url}/auth/v1/token?grant_type=password",
                headers={"apikey": key, "Content-Type": "application/json"},
                json={"email": email, "password": password},
            )
    except httpx.HTTPError as exc:
        raise IdentityProviderError(502, f"Não foi possível comunicar com o Supabase Auth: {exc}") from exc
    if response.status_code != 200:
        raise IdentityProviderError(401, _message(response, "E-mail ou senha inválidos."))
    try:
        payload = response.json()
    except ValueError as exc:
        raise IdentityProviderError(502, "O Supabase Auth retornou uma resposta inválida.") from exc
    if not (payload.get("user") or {}).get("id"):
        raise IdentityProviderError(502, "O Supabase Auth não retornou a identidade do usuário.")
    return payload

