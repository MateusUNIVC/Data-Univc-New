from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterator

import requests

LOGGER = logging.getLogger("univc.dadm.tallos.client")

TALLOS_BASE_URL = os.getenv("TALLOS_BASE_URL", "https://api.tallos.com.br").rstrip("/")
TALLOS_PAGE_LIMIT = min(49, max(1, int(os.getenv("TALLOS_PAGE_LIMIT", "49"))))
TALLOS_REQUEST_TIMEOUT = max(5, int(os.getenv("TALLOS_REQUEST_TIMEOUT", "60")))
TALLOS_REQUEST_RETRIES = max(1, int(os.getenv("TALLOS_REQUEST_RETRIES", "4")))
TALLOS_CHUNK_DAYS = min(90, max(1, int(os.getenv("TALLOS_CHUNK_DAYS", "90"))))


class DADMTallosAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class DADMTallosPage:
    docs: list[dict]
    page: int
    pages: int
    total: int
    limit: int
    start_date: date
    end_date: date


@dataclass(frozen=True)
class DADMTallosPlan:
    """Snapshot do tamanho da sincronização antes de processar os fatos.

    O total é fixado a partir da primeira página de cada bloco de datas. Isso
    impede que a barra de progresso retroceda quando um novo bloco é descoberto.
    """

    first_pages: list[DADMTallosPage]
    total_expected: int
    pages_expected: int


def token_configured() -> bool:
    return bool(os.getenv("TALLOS_API_TOKEN", "").strip())


def _token() -> str:
    value = os.getenv("TALLOS_API_TOKEN", "").strip()
    if not value:
        raise DADMTallosAPIError("TALLOS_API_TOKEN não foi configurado no backend.")
    return value


def iter_date_chunks(start_date: date, end_date: date, *, max_inclusive_days: int = TALLOS_CHUNK_DAYS) -> Iterator[tuple[date, date]]:
    if end_date < start_date:
        raise ValueError("A data final não pode ser anterior à data inicial.")
    cursor = start_date
    delta = timedelta(days=max(1, max_inclusive_days) - 1)
    while cursor <= end_date:
        chunk_end = min(end_date, cursor + delta)
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


class DADMTallosClient:
    """Cliente defensivo de ``GET /v4/reports``.

    O ambiente validado da UNIVC devolve ``docs/total/limit/page/pages`` e
    rejeita ``limit >= 50``. O limite 49 fica explícito no contrato para evitar
    regressões e chamadas desnecessariamente pesadas.
    """

    def __init__(self, *, token: str | None = None, session: requests.Session | None = None):
        self.token = (token or _token()).strip()
        self.session = session or requests.Session()

    def _request(self, params: dict, *, path: str = "/v4/reports") -> dict | list:
        url = f"{TALLOS_BASE_URL}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(1, TALLOS_REQUEST_RETRIES + 1):
            try:
                response = self.session.get(url, params=params, headers=headers, timeout=TALLOS_REQUEST_TIMEOUT)
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= TALLOS_REQUEST_RETRIES:
                    break
                time.sleep(min(8, 2 ** (attempt - 1)))
                continue

            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise DADMTallosAPIError("A API TALLOS retornou JSON inválido.") from exc
                if not isinstance(payload, (dict, list)):
                    raise DADMTallosAPIError("A API TALLOS retornou um formato inesperado.")
                return payload

            if response.status_code in {429, 500, 502, 503, 504} and attempt < TALLOS_REQUEST_RETRIES:
                retry_after = response.headers.get("Retry-After")
                try:
                    wait = float(retry_after) if retry_after else min(8, 2 ** (attempt - 1))
                except ValueError:
                    wait = min(8, 2 ** (attempt - 1))
                time.sleep(max(0.5, wait))
                continue

            body = response.text[:700].strip()
            raise DADMTallosAPIError(
                f"TALLOS respondeu HTTP {response.status_code}. " + (body or "Sem detalhes adicionais.")
            )

        raise DADMTallosAPIError(f"Não foi possível comunicar com a TALLOS: {last_error or 'erro de rede'}")


    def test_connection(self) -> dict:
        """Valida autenticação sem expor o token ao chamador.

        O endpoint de colaboradores já foi usado na homologação inicial da UNIVC e
        é suficiente para provar que o Bearer está aceito antes de iniciar uma
        sincronização potencialmente longa.
        """
        payload = self._request({}, path="/v2/employees")
        if isinstance(payload, list):
            count = len(payload)
        elif isinstance(payload, dict):
            docs = payload.get("docs") or payload.get("data") or payload.get("employees")
            count = len(docs) if isinstance(docs, list) else None
        else:
            count = None
        return {
            "ok": True,
            "endpoint": "/v2/employees",
            "employees_detected": count,
        }

    def fetch_report_page(self, start_date: date, end_date: date, page: int = 1) -> DADMTallosPage:
        payload = self._request({
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "page": max(1, int(page)),
            "limit": TALLOS_PAGE_LIMIT,
        })
        if not isinstance(payload, dict):
            raise DADMTallosAPIError("A API TALLOS retornou um formato inesperado para /v4/reports.")
        docs = payload.get("docs") or []
        if not isinstance(docs, list):
            raise DADMTallosAPIError("A resposta TALLOS não possui uma lista válida em 'docs'.")
        current_page = int(payload.get("page") or page)
        pages = max(1, int(payload.get("pages") or current_page))
        total = max(0, int(payload.get("total") or len(docs)))
        limit = int(payload.get("limit") or TALLOS_PAGE_LIMIT)
        return DADMTallosPage(
            docs=[row for row in docs if isinstance(row, dict)],
            page=current_page,
            pages=pages,
            total=total,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )

    def plan_report_pages(self, start_date: date, end_date: date) -> DADMTallosPlan:
        first_pages: list[DADMTallosPage] = []
        total_expected = 0
        pages_expected = 0
        for chunk_start, chunk_end in iter_date_chunks(start_date, end_date):
            first = self.fetch_report_page(chunk_start, chunk_end, 1)
            first_pages.append(first)
            total_expected += int(first.total or 0)
            pages_expected += int(first.pages or 1)
        return DADMTallosPlan(
            first_pages=first_pages,
            total_expected=total_expected,
            pages_expected=pages_expected,
        )

    def iter_report_pages(self, start_date: date, end_date: date) -> Iterator[DADMTallosPage]:
        for chunk_start, chunk_end in iter_date_chunks(start_date, end_date):
            page = 1
            while True:
                current = self.fetch_report_page(chunk_start, chunk_end, page)
                yield current
                if current.page >= current.pages or not current.docs:
                    break
                page = current.page + 1
