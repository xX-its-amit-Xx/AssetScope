"""Landscape persistence: save completed landscapes to Postgres (jsonb) so runs
are durable, listable, and re-openable without re-running the agent.

Mirrors the retrieval store pattern: a Postgres-backed :class:`LandscapeStore`
with an :class:`InMemoryLandscapeStore` fallback, selected by
:func:`get_landscape_store` so the API degrades gracefully when no DB is present.
This is the foundation for the history library, diff-over-time and watchlists.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Protocol

from assetscope.config import get_settings
from assetscope.models import Landscape

logger = logging.getLogger("assetscope.storage")

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS landscapes (
    id             TEXT PRIMARY KEY,
    query          TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    backend        TEXT NOT NULL DEFAULT '',
    model          TEXT NOT NULL DEFAULT '',
    tool_calls     INT NOT NULL DEFAULT 0,
    n_assets       INT NOT NULL DEFAULT 0,
    dropped_claims INT NOT NULL DEFAULT 0,
    landscape      JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS landscapes_created_at ON landscapes (created_at DESC);
"""


def _summary_row(id_: str, ls: Landscape, created_at: Any) -> dict[str, Any]:
    return {
        "id": id_,
        "query": ls.query,
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        "n_assets": len(ls.assets),
        "tool_calls": ls.tool_calls,
        "dropped_claims": ls.dropped_claims,
    }


class LandscapeStoreP(Protocol):
    def save(self, landscape: Landscape, *, backend: str = "", model: str = "") -> str: ...
    def list(self, limit: int = 50) -> list[dict]: ...
    def get(self, id_: str) -> dict | None: ...
    @property
    def backend(self) -> str: ...


class LandscapeStore:
    """PostgreSQL (jsonb) backend."""

    backend = "postgres"

    def __init__(self, dsn: str | None = None) -> None:
        import psycopg

        settings = get_settings()
        self._conn = psycopg.connect(dsn or settings.database_url, autocommit=True)
        with self._conn.cursor() as cur:
            cur.execute(CREATE_SQL)

    def save(self, landscape: Landscape, *, backend: str = "", model: str = "") -> str:
        id_ = uuid.uuid4().hex
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO landscapes
                    (id, query, backend, model, tool_calls, n_assets, dropped_claims, landscape)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    id_, landscape.query, backend, model, landscape.tool_calls,
                    len(landscape.assets), landscape.dropped_claims,
                    json.dumps(landscape.model_dump(mode="json")),
                ),
            )
        return id_

    def list(self, limit: int = 50) -> list[dict]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, query, created_at, n_assets, tool_calls, dropped_claims
                FROM landscapes ORDER BY created_at DESC LIMIT %s
                """,
                (min(max(limit, 1), 500),),
            )
            return [
                {"id": r[0], "query": r[1], "created_at": r[2].isoformat(),
                 "n_assets": r[3], "tool_calls": r[4], "dropped_claims": r[5]}
                for r in cur.fetchall()
            ]

    def get(self, id_: str) -> dict | None:
        with self._conn.cursor() as cur:
            cur.execute("SELECT landscape FROM landscapes WHERE id = %s", (id_,))
            row = cur.fetchone()
            return row[0] if row else None


class InMemoryLandscapeStore:
    """Fallback store (lost on restart) used when no database is reachable."""

    backend = "in-memory"

    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}
        self._order: list[str] = []

    def save(self, landscape: Landscape, *, backend: str = "", model: str = "") -> str:
        from datetime import UTC, datetime

        id_ = uuid.uuid4().hex
        self._rows[id_] = {
            "summary": _summary_row(id_, landscape, datetime.now(UTC)),
            "landscape": landscape.model_dump(mode="json"),
        }
        self._order.insert(0, id_)
        return id_

    def list(self, limit: int = 50) -> list[dict]:
        return [self._rows[i]["summary"] for i in self._order[: min(max(limit, 1), 500)]]

    def get(self, id_: str) -> dict | None:
        row = self._rows.get(id_)
        return row["landscape"] if row else None


_store: LandscapeStoreP | None = None


def get_landscape_store(prefer_db: bool = True) -> LandscapeStoreP:
    """Process-wide cached landscape store (Postgres if reachable, else in-memory)."""
    global _store
    if _store is not None:
        return _store
    if prefer_db:
        try:
            _store = LandscapeStore()
            return _store
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.warning("Postgres unavailable for landscape store (%s); using in-memory.", exc)
    _store = InMemoryLandscapeStore()
    return _store
