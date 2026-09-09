from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Mapping

JWT_ALGORITHM = "HS256"
JWT_ISSUER = os.getenv("DATA_UNIVC_JWT_ISSUER", "data-univc")
JWT_AUDIENCE = os.getenv("DATA_UNIVC_JWT_AUDIENCE", "data-univc-web")
ACCESS_TOKEN_TTL_SECONDS = max(60, int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "600")))
JWT_CLOCK_SKEW_SECONDS = max(0, int(os.getenv("JWT_CLOCK_SKEW_SECONDS", "30")))


class AccessTokenError(ValueError):
    """Raised when a Data UNIVC access token cannot be trusted."""


class AccessTokenExpired(AccessTokenError):
    """Raised when a Data UNIVC access token is valid but expired."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except Exception as exc:
        raise AccessTokenError("Token de acesso malformado.") from exc


def _single_secret() -> str:
    return os.getenv("DATA_UNIVC_JWT_SECRET", "")


def _keyring() -> tuple[str, dict[str, bytes]]:
    """Return active KID plus signing/verification keys.

    DATA_UNIVC_JWT_KEYS_JSON may contain e.g. {"2026-09":"secret...","2026-12":"secret..."}.
    DATA_UNIVC_JWT_ACTIVE_KID selects the issuer key. DATA_UNIVC_JWT_SECRET remains
    the compatibility key for access tokens issued before KID support.
    """
    raw = os.getenv("DATA_UNIVC_JWT_KEYS_JSON", "").strip()
    keys: dict[str, bytes] = {}
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("DATA_UNIVC_JWT_KEYS_JSON não contém JSON válido.") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("DATA_UNIVC_JWT_KEYS_JSON deve ser um objeto {kid: segredo}.")
        for kid, secret in parsed.items():
            key_id = str(kid or "").strip()
            value = str(secret or "")
            if not key_id or len(value) < 32:
                raise RuntimeError("Cada chave JWT deve ter um KID e segredo com pelo menos 32 caracteres.")
            keys[key_id] = value.encode("utf-8")

    legacy = _single_secret()
    if legacy:
        if len(legacy) < 32:
            raise RuntimeError("DATA_UNIVC_JWT_SECRET deve possuir pelo menos 32 caracteres.")
        keys.setdefault("legacy", legacy.encode("utf-8"))

    if not keys:
        raise RuntimeError(
            "Configure DATA_UNIVC_JWT_SECRET ou DATA_UNIVC_JWT_KEYS_JSON com segredos de pelo menos 32 caracteres."
        )

    configured_active = os.getenv("DATA_UNIVC_JWT_ACTIVE_KID", "").strip()
    if configured_active:
        if configured_active not in keys:
            raise RuntimeError("DATA_UNIVC_JWT_ACTIVE_KID não existe em DATA_UNIVC_JWT_KEYS_JSON.")
        active = configured_active
    elif raw:
        # JSON preserves insertion order; operators can explicitly set ACTIVE_KID
        # when rotating. Falling back to the first key keeps local setup simple.
        active = next(iter(keys))
    else:
        active = "legacy"
    return active, keys


def issue_access_token(claims: Mapping[str, Any], *, now: int | None = None) -> tuple[str, int]:
    issued_at = int(time.time() if now is None else now)
    expires_at = issued_at + ACCESS_TOKEN_TTL_SECONDS
    active_kid, keys = _keyring()
    header = {"alg": JWT_ALGORITHM, "typ": "JWT", "kid": active_kid}
    payload = {
        **dict(claims),
        "iat": issued_at,
        "exp": expires_at,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    header_segment = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_segment = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = hmac.new(keys[active_kid], signing_input, hashlib.sha256).digest()
    return f"{header_segment}.{payload_segment}.{_b64url_encode(signature)}", expires_at


def decode_access_token(token: str, *, now: int | None = None) -> dict[str, Any]:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise AccessTokenError("Token de acesso malformado.") from exc

    try:
        header = json.loads(_b64url_decode(header_segment))
        payload = json.loads(_b64url_decode(payload_segment))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise AccessTokenError("Token de acesso malformado.") from exc

    if header.get("alg") != JWT_ALGORITHM or header.get("typ") != "JWT":
        raise AccessTokenError("Algoritmo de token não permitido.")

    _, keys = _keyring()
    kid = str(header.get("kid") or "").strip()
    candidate_keys: list[bytes]
    if kid:
        key = keys.get(kid)
        if not key:
            raise AccessTokenError("Chave de assinatura do token não é mais aceita.")
        candidate_keys = [key]
    else:
        # v0.9.0-v0.9.4 JWTs did not carry a KID. Accept only the explicit
        # DATA_UNIVC_JWT_SECRET compatibility key until those short tokens expire.
        legacy = _single_secret()
        if len(legacy) < 32:
            raise AccessTokenError("Token legado sem KID não é mais aceito.")
        candidate_keys = [legacy.encode("utf-8")]

    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    supplied = _b64url_decode(signature_segment)
    if not any(hmac.compare_digest(hmac.new(key, signing_input, hashlib.sha256).digest(), supplied) for key in candidate_keys):
        raise AccessTokenError("Assinatura do token inválida.")

    if payload.get("iss") != JWT_ISSUER or payload.get("aud") != JWT_AUDIENCE:
        raise AccessTokenError("Emissor ou audiência do token inválidos.")

    required = ("sub", "sid", "email", "role", "directorate_id", "directorate_code", "exp", "iat")
    if any(payload.get(key) in (None, "") for key in required):
        raise AccessTokenError("Token de acesso incompleto.")

    current = int(time.time() if now is None else now)
    try:
        expires_at = int(payload["exp"])
        issued_at = int(payload["iat"])
    except (TypeError, ValueError) as exc:
        raise AccessTokenError("Datas do token inválidas.") from exc

    if issued_at > current + JWT_CLOCK_SKEW_SECONDS:
        raise AccessTokenError("Token emitido no futuro.")
    if expires_at <= current - JWT_CLOCK_SKEW_SECONDS:
        raise AccessTokenExpired("Sessão expirada. Renove para continuar.")
    return payload
