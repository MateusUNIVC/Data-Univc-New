from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class IdentityAdminError(Exception):
    status_code: int
    message: str

    def __str__(self) -> str:
        return self.message


def _config() -> tuple[str, str]:
    """Return the Supabase project URL and the server-side admin API key.

    New Supabase projects should use ``SUPABASE_SECRET_KEY=sb_secret_...``.
    ``SUPABASE_SERVICE_ROLE_KEY`` is kept as a compatibility fallback for
    deployments that still use the legacy service_role JWT.  A temporarily
    misnamed ``sb_secret_...`` value in the legacy variable also remains safe:
    header construction is based on the key format, not on the env var name.
    """
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = (
        os.getenv("SUPABASE_SECRET_KEY", "").strip()
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    missing = []
    if not url:
        missing.append("SUPABASE_URL")
    if not key:
        missing.append("SUPABASE_SECRET_KEY")
    if missing:
        suffix = " (ou SUPABASE_SERVICE_ROLE_KEY legado)" if "SUPABASE_SECRET_KEY" in missing else ""
        raise IdentityAdminError(
            503,
            "Administração de identidades indisponível. Configure no backend: "
            + ", ".join(missing)
            + suffix
            + ".",
        )
    return url, key


def _is_legacy_jwt_key(key: str) -> bool:
    """Legacy anon/service_role keys are JWTs; new sb_* API keys are not."""
    value = str(key or "").strip()
    return value.startswith("eyJ") and value.count(".") == 2


def _headers(key: str, *, content_type: str = "application/json") -> dict[str, str]:
    """Build Supabase API headers without treating sb_secret_* as a JWT.

    Supabase publishable/secret API keys belong in ``apikey``.  Only the
    legacy JWT-shaped service_role key is also sent as a Bearer token for
    backwards compatibility with older projects.
    """
    headers = {
        "apikey": key,
        "Content-Type": content_type,
    }
    if _is_legacy_jwt_key(key):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _message(response: httpx.Response, fallback: str) -> str:
    try:
        payload = response.json()
    except ValueError:
        return fallback
    if isinstance(payload, dict):
        return str(
            payload.get("msg")
            or payload.get("message")
            or payload.get("error_description")
            or payload.get("error")
            or fallback
        )
    return fallback


def _request(
    method: str,
    path: str,
    *,
    json: dict | None = None,
    content: bytes | None = None,
    content_type: str = "application/json",
) -> httpx.Response:
    url, key = _config()
    try:
        with httpx.Client(timeout=20) as client:
            response = client.request(
                method,
                f"{url}{path}",
                headers=_headers(key, content_type=content_type),
                json=json,
                content=content,
            )
    except httpx.HTTPError as exc:
        raise IdentityAdminError(502, f"Não foi possível comunicar com o Supabase: {exc}") from exc
    return response


def create_identity(*, email: str, password: str, name: str) -> dict:
    response = _request(
        "POST",
        "/auth/v1/admin/users",
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": name, "name": name},
        },
    )
    if response.status_code not in {200, 201}:
        status = 409 if response.status_code == 409 else (422 if response.status_code in {400, 422} else 502)
        raise IdentityAdminError(status, _message(response, "Não foi possível criar a identidade no Supabase Auth."))
    try:
        payload = response.json()
    except ValueError as exc:
        raise IdentityAdminError(502, "O Supabase Auth retornou uma resposta inválida ao criar o usuário.") from exc
    if not payload.get("id"):
        raise IdentityAdminError(502, "O Supabase Auth não retornou o identificador do novo usuário.")
    return payload


def update_identity(
    user_id: str,
    *,
    email: str | None = None,
    password: str | None = None,
    name: str | None = None,
) -> dict:
    payload: dict = {}
    if email is not None:
        payload["email"] = email
        payload["email_confirm"] = True
    if password:
        payload["password"] = password
    if name is not None:
        payload["user_metadata"] = {"full_name": name, "name": name}
    if not payload:
        return {"id": user_id}
    response = _request("PUT", f"/auth/v1/admin/users/{quote(str(user_id), safe='')}", json=payload)
    if response.status_code != 200:
        status = 409 if response.status_code == 409 else (422 if response.status_code in {400, 422} else 502)
        raise IdentityAdminError(status, _message(response, "Não foi possível atualizar a identidade no Supabase Auth."))
    try:
        result = response.json()
    except ValueError as exc:
        raise IdentityAdminError(502, "O Supabase Auth retornou uma resposta inválida ao atualizar o usuário.") from exc
    return result


def delete_identity(user_id: str) -> None:
    response = _request("DELETE", f"/auth/v1/admin/users/{quote(str(user_id), safe='')}")
    if response.status_code not in {200, 204, 404}:
        raise IdentityAdminError(502, _message(response, "Não foi possível remover a identidade criada durante o rollback."))


def _avatar_bucket() -> str:
    return os.getenv("SUPABASE_AVATAR_BUCKET", "data-univc-avatars").strip() or "data-univc-avatars"


def ensure_avatar_bucket() -> str:
    bucket = _avatar_bucket()
    response = _request("HEAD", f"/storage/v1/bucket/{quote(bucket, safe='')}")
    if response.status_code == 200:
        return bucket
    if response.status_code != 404:
        raise IdentityAdminError(502, _message(response, "Não foi possível consultar o armazenamento de avatares."))
    create = _request(
        "POST",
        "/storage/v1/bucket",
        json={
            "id": bucket,
            "name": bucket,
            "public": False,
            "file_size_limit": 2 * 1024 * 1024,
            "allowed_mime_types": ["image/jpeg", "image/png", "image/webp"],
        },
    )
    if create.status_code not in {200, 201}:
        raise IdentityAdminError(502, _message(create, "Não foi possível criar o armazenamento privado de avatares."))
    return bucket


def upload_avatar(*, user_id: str, data: bytes, content_type: str) -> str:
    bucket = ensure_avatar_bucket()
    object_path = f"users/{user_id}/avatar"
    response = _request(
        "POST",
        f"/storage/v1/object/{quote(bucket, safe='')}/{quote(object_path, safe='/')}",
        content=data,
        content_type=content_type,
    )
    if response.status_code in {400, 409}:
        # The deterministic object already exists: replace it using Storage's
        # documented update endpoint instead of deleting it first.
        response = _request(
            "PUT",
            f"/storage/v1/object/{quote(bucket, safe='')}/{quote(object_path, safe='/')}",
            content=data,
            content_type=content_type,
        )
    if response.status_code not in {200, 201}:
        raise IdentityAdminError(502, _message(response, "Não foi possível salvar a foto de perfil."))
    return object_path


def download_avatar(path: str) -> tuple[bytes, str]:
    bucket = _avatar_bucket()
    response = _request(
        "GET",
        f"/storage/v1/object/authenticated/{quote(bucket, safe='')}/{quote(path, safe='/')}",
        content_type="application/octet-stream",
    )
    if response.status_code == 404:
        raise IdentityAdminError(404, "Foto de perfil não encontrada.")
    if response.status_code != 200:
        raise IdentityAdminError(502, _message(response, "Não foi possível carregar a foto de perfil."))
    content_type = response.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
    return response.content, content_type


def delete_avatar(path: str) -> None:
    bucket = _avatar_bucket()
    response = _request(
        "DELETE",
        f"/storage/v1/object/{quote(bucket, safe='')}/{quote(path, safe='/')}",
    )
    if response.status_code not in {200, 204, 404}:
        raise IdentityAdminError(502, _message(response, "Não foi possível remover a foto de perfil."))
