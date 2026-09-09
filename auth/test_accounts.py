from __future__ import annotations

import os
import uuid
from dataclasses import dataclass


_TEST_NAMESPACE = uuid.UUID("64821b7e-f75e-4c80-948c-c71ad15fdcdf")


@dataclass(frozen=True)
class LocalTestAccount:
    code: str
    email: str
    name: str
    global_role: str = "DIRECTORATE"
    access: str = "EDIT"
    directorate_code: str | None = None

    @property
    def home_directorate_code(self) -> str:
        return str(self.directorate_code or self.code).strip().upper()

    @property
    def user_id(self) -> str:
        return str(uuid.uuid5(_TEST_NAMESPACE, self.email.casefold()))


LEGACY_LOCAL_TEST_EMAILS: tuple[str, ...] = (
    "rodrigo.ghiradelli@ivc.br",
)


LOCAL_TEST_ACCOUNTS: tuple[LocalTestAccount, ...] = (
    LocalTestAccount("DTNH", "dtnh@ivc.br", "Diretoria de Tecnologia, Negócios e Humanidades"),
    LocalTestAccount("DCS", "dcs@ivc.br", "Diretoria de Ciências da Saúde"),
    LocalTestAccount("DADM", "dadm@ivc.br", "DADM - Setores autorizados"),
    LocalTestAccount("DADM_FULL", "rodrigo.ghirardelli@ivc.br", "Rodrigo Ghirardelli", directorate_code="DADM"),
    LocalTestAccount("DPE", "dpe@ivc.br", "Diretoria de Planejamento Econômico e Oferta"),
    LocalTestAccount("DM", "dm@ivc.br", "Diretoria de Mestrado"),
    LocalTestAccount("REITORIA", "reitoria@ivc.br", "Reitoria", global_role="REITORIA"),
)


def local_test_auth_enabled() -> bool:
    enabled = os.getenv("DATA_UNIVC_LOCAL_TEST_AUTH", "false").strip().lower() in {"1", "true", "yes", "on"}
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    # Never permit the local fixed-credential provider in a production process.
    return enabled and environment not in {"prod", "production"}


def local_test_password() -> str:
    return os.getenv("DATA_UNIVC_TEST_PASSWORD", "")


def account_for_email(email: str | None) -> LocalTestAccount | None:
    normalized = str(email or "").strip().casefold()
    return next((account for account in LOCAL_TEST_ACCOUNTS if account.email.casefold() == normalized), None)


def public_test_accounts() -> list[dict[str, str]]:
    return [
        {
            "code": account.code,
            "email": account.email,
            "name": account.name,
            "role": account.global_role,
            "access": account.access,
        }
        for account in LOCAL_TEST_ACCOUNTS
    ]
