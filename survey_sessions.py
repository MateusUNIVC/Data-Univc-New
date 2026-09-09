from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

from survey_sei import SEIInstitutionalEvaluationConnector


@dataclass
class _SessionEntry:
    connector: SEIInstitutionalEvaluationConnector
    owner_user_id: str
    touched_at: float


class SurveySEISessionRegistry:
    """Sessões do SEI somente em memória e vinculadas ao usuário do Data UNIVC.

    Credenciais, JSESSIONID e ViewState nunca são persistidos. O vínculo com o
    usuário autenticado impede que um token local de uma sessão seja reutilizado
    por outro usuário do Data UNIVC.
    """

    def __init__(self, *, ttl_seconds: int = 30 * 60) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, _SessionEntry] = {}
        self._lock = threading.RLock()

    def _cleanup(self) -> None:
        now = time.monotonic()
        expired = [
            token for token, entry in self._sessions.items()
            if now - entry.touched_at > self.ttl_seconds
        ]
        for token in expired:
            entry = self._sessions.pop(token, None)
            if entry:
                entry.connector.close()

    def create(self, username: str, password: str, *, owner_user_id: str) -> str:
        connector = SEIInstitutionalEvaluationConnector()
        connector.login(username, password)
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._cleanup()
            self._sessions[token] = _SessionEntry(
                connector=connector,
                owner_user_id=str(owner_user_id),
                touched_at=time.monotonic(),
            )
        return token

    def get(self, token: str, *, owner_user_id: str) -> SEIInstitutionalEvaluationConnector:
        with self._lock:
            self._cleanup()
            entry = self._sessions.get(token)
            if not entry or entry.owner_user_id != str(owner_user_id):
                raise KeyError("Sessão do SEI expirada, inexistente ou pertencente a outro usuário.")
            entry.touched_at = time.monotonic()
            return entry.connector

    def remove(self, token: str, *, owner_user_id: str) -> None:
        with self._lock:
            entry = self._sessions.get(token)
            if entry and entry.owner_user_id == str(owner_user_id):
                self._sessions.pop(token, None)
            else:
                entry = None
        if entry:
            entry.connector.close()

    def count(self) -> int:
        with self._lock:
            self._cleanup()
            return len(self._sessions)
