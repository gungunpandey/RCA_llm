"""
In-memory session cache for the two-phase RCA pipeline.

Holds the intermediate state (failure text, domain insights, history,
image analysis, clarifying questions) between /analyze-prepare-stream and
/analyze-finalize-stream.

Single-process, single-server design — replace with Redis only if the
deployment is ever scaled horizontally.
"""

import time
import uuid
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from models.tool_results import DomainInsightsSummary, ClarifyingQuestion


DEFAULT_TTL_SECONDS = 15 * 60  # 15 minutes


# ── Errors ──────────────────────────────────────────────────────────────────

class SessionError(Exception):
    """Base exception for session cache errors."""


class SessionNotFoundError(SessionError):
    """Session id is not present in the cache."""


class SessionExpiredError(SessionError):
    """Session was present but has exceeded its TTL."""


# ── Session record ──────────────────────────────────────────────────────────

@dataclass
class RCASession:
    """All intermediate state needed to finalize an RCA after the chatbot step."""
    session_id: str
    created_at: float
    equipment_name: str
    failure_text: str
    symptoms: List[str]
    domain_insights: DomainInsightsSummary
    history_context: str
    history_matches: list
    image_analysis: Optional[dict]
    selected_agents: List[str]
    questions: List[ClarifyingQuestion] = field(default_factory=list)


# ── Cache ───────────────────────────────────────────────────────────────────

class SessionCache:
    """Thread-safe in-memory cache with lazy TTL eviction."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._ttl = ttl_seconds
        self._store: Dict[str, RCASession] = {}
        self._lock = threading.Lock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def create(
        self,
        equipment_name: str,
        failure_text: str,
        symptoms: List[str],
        domain_insights: DomainInsightsSummary,
        history_context: str,
        history_matches: list,
        image_analysis: Optional[dict],
        selected_agents: List[str],
        questions: List[ClarifyingQuestion],
    ) -> RCASession:
        """Insert a new session and return the full record (caller wants both id and expires_at)."""
        session_id = uuid.uuid4().hex
        session = RCASession(
            session_id=session_id,
            created_at=time.time(),
            equipment_name=equipment_name,
            failure_text=failure_text,
            symptoms=symptoms,
            domain_insights=domain_insights,
            history_context=history_context,
            history_matches=history_matches,
            image_analysis=image_analysis,
            selected_agents=selected_agents,
            questions=questions,
        )
        with self._lock:
            self._sweep_locked()
            self._store[session_id] = session
        return session

    def get(self, session_id: str) -> RCASession:
        """Retrieve session; raises SessionNotFoundError or SessionExpiredError."""
        with self._lock:
            session = self._store.get(session_id)
            if session is None:
                raise SessionNotFoundError(f"Session not found: {session_id}")
            if self._is_expired(session):
                del self._store[session_id]
                raise SessionExpiredError(f"Session expired: {session_id}")
            return session

    def evict(self, session_id: str) -> None:
        """Remove a session (idempotent)."""
        with self._lock:
            self._store.pop(session_id, None)

    def expires_at(self, session: RCASession) -> float:
        """Absolute unix timestamp when this session will expire."""
        return session.created_at + self._ttl

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    # ── internals ───────────────────────────────────────────────────────────

    def _is_expired(self, session: RCASession) -> bool:
        return (time.time() - session.created_at) > self._ttl

    def _sweep_locked(self) -> None:
        """Remove all expired sessions. Caller must hold the lock."""
        now = time.time()
        expired = [
            sid for sid, s in self._store.items()
            if (now - s.created_at) > self._ttl
        ]
        for sid in expired:
            del self._store[sid]
