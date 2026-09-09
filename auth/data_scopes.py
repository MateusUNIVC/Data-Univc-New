from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DepartmentGrant:
    key: str
    name: str
    aliases: tuple[str, ...] = ()

    @property
    def scope_keys(self) -> tuple[str, ...]:
        # TALLOS persists the full source identifier (for example
        # ``financeiro_12c84``).  The short hexadecimal suffixes are kept only
        # as backwards-compatible aliases for older local fixtures/imports.
        return (self.key, *self.aliases)


DADM_LIMITED_DEPARTMENTS: tuple[DepartmentGrant, ...] = (
    DepartmentGrant("financeiro_12c84", "Financeiro", ("12c84",)),
    DepartmentGrant("secretaria_academica_a967b", "Secretaria Acadêmica", ("a967b",)),
    DepartmentGrant("mestrado_8155e", "Mestrado", ("8155e",)),
    DepartmentGrant("negociacao_b623", "Negociação", ("b623",)),
    DepartmentGrant("prouni_nbolsa_fies_9bc56", "Prouni / Nbolsa / Fies", ("9bc56",)),
    DepartmentGrant("estagio_80bc4", "Estágio", ("80bc4",)),
)

DADM_LIMITED_USERS = {
    "dadm@ivc.br": DADM_LIMITED_DEPARTMENTS,
}

DADM_FULL_USERS = {
    "rodrigo.ghirardelli@ivc.br",
}


def normalize_department_key(value: str | None) -> str:
    return str(value or "").strip().casefold()


def dadm_department_scope(email: str | None, *, global_access: bool = False) -> tuple[str, ...] | None:
    """Return None for full DADM access or a tuple of permitted TALLOS department keys."""
    if global_access:
        return None
    normalized_email = str(email or "").strip().casefold()
    if normalized_email in DADM_FULL_USERS:
        return None
    grants = DADM_LIMITED_USERS.get(normalized_email)
    if grants is None:
        # Existing/future DADM identities keep their current full scope unless explicitly restricted.
        return None
    return tuple(key for item in grants for key in item.scope_keys)


def dadm_has_full_data_access(email: str | None, *, global_access: bool = False) -> bool:
    return dadm_department_scope(email, global_access=global_access) is None


def dadm_department_grant(value: str | None) -> DepartmentGrant | None:
    key = normalize_department_key(value)
    if not key:
        return None
    for grant in DADM_LIMITED_DEPARTMENTS:
        if key in {normalize_department_key(item) for item in grant.scope_keys}:
            return grant
    return None


def dadm_preferred_department_name(value: str | None) -> str | None:
    grant = dadm_department_grant(value)
    return grant.name if grant else None


def department_allowed(value: str | None, allowed_departments: tuple[str, ...] | None) -> bool:
    if allowed_departments is None:
        return True
    key = normalize_department_key(value)
    return bool(key) and key in {normalize_department_key(item) for item in allowed_departments}


def dadm_scope_payload(email: str | None, *, global_access: bool = False) -> dict:
    allowed = dadm_department_scope(email, global_access=global_access)
    if allowed is None:
        return {"full": True, "departments": []}
    allowed_keys = {normalize_department_key(item) for item in allowed}
    return {
        "full": False,
        "departments": [
            {"key": item.key, "name": item.name}
            for item in DADM_LIMITED_DEPARTMENTS
            if normalize_department_key(item.key) in allowed_keys
        ],
    }
