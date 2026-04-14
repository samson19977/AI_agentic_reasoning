"""SQLite-backed persistence for jobs, events, and pipeline states.

Replaces the in-memory dicts in jobs.py with durable storage.
The DB file location is controlled by the DB_PATH env var (default: data/jobs.db).

Schema
------
jobs   — one row per job (mirrors JobResult)
events — append-only event log per job
states — serialised SharedState JSON for completed jobs
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from app.core import config
from app.models.api import JobResult, JobStatus
from app.models.state import EvaluationScores, SharedState

logger = logging.getLogger(__name__)

# ── One connection per thread ─────────────────────────────────────────────────
_local = threading.local()

_DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id       TEXT PRIMARY KEY,
    status       TEXT NOT NULL,
    question     TEXT NOT NULL,
    report       TEXT NOT NULL DEFAULT '',
    error        TEXT NOT NULL DEFAULT '',
    sources_count  INTEGER NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    themes_count   INTEGER NOT NULL DEFAULT 0,
    eval_coverage          REAL,
    eval_faithfulness      REAL,
    eval_hallucination     REAL,
    eval_usefulness        REAL,
    eval_reasoning         TEXT,
    created_at   REAL NOT NULL DEFAULT (unixepoch('now','subsec'))
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT NOT NULL REFERENCES jobs(job_id),
    event_type TEXT NOT NULL,
    data       TEXT NOT NULL DEFAULT '{}',
    ts         REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS states (
    job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),
    body   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS events_job_id ON events(job_id);
"""


def _db_path() -> Path:
    path = Path(config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    """Return a per-thread sqlite3 connection (lazy init)."""
    if not getattr(_local, "conn", None):
        conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_DDL)
        conn.commit()
        _local.conn = conn
    yield _local.conn


# ── Jobs ──────────────────────────────────────────────────────────────────────

def db_upsert_job(job: JobResult) -> None:
    """Insert or replace a job row."""
    ev = job.evaluation
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                job_id, status, question, report, error,
                sources_count, evidence_count, themes_count,
                eval_coverage, eval_faithfulness, eval_hallucination,
                eval_usefulness, eval_reasoning, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(job_id) DO UPDATE SET
                status            = excluded.status,
                report            = excluded.report,
                error             = excluded.error,
                sources_count     = excluded.sources_count,
                evidence_count    = excluded.evidence_count,
                themes_count      = excluded.themes_count,
                eval_coverage     = excluded.eval_coverage,
                eval_faithfulness = excluded.eval_faithfulness,
                eval_hallucination= excluded.eval_hallucination,
                eval_usefulness   = excluded.eval_usefulness,
                eval_reasoning    = excluded.eval_reasoning
            """,
            (
                job.job_id, job.status.value, job.question,
                job.report, job.error,
                job.sources_count, job.evidence_count, job.themes_count,
                ev.coverage if ev else None,
                ev.faithfulness if ev else None,
                ev.hallucination_rate if ev else None,
                ev.usefulness if ev else None,
                ev.reasoning if ev else None,
                time.time(),
            ),
        )
        conn.commit()


def db_get_job(job_id: str) -> JobResult | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return _row_to_job(row)


def db_list_jobs() -> list[JobResult]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    return [_row_to_job(r) for r in rows]


def db_delete_job(job_id: str) -> bool:
    """Delete a job and its associated events and state. Returns True if found."""
    with _conn() as conn:
        rows_deleted = conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,)).rowcount
        conn.execute("DELETE FROM events WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM states WHERE job_id = ?", (job_id,))
        conn.commit()
    return rows_deleted > 0


def db_clear_all_jobs() -> int:
    """Delete all jobs, events, and states. Returns the number of jobs deleted."""
    with _conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM states")
        conn.execute("DELETE FROM jobs")
        conn.commit()
    return count


def _row_to_job(row: sqlite3.Row) -> JobResult:
    eval_scores = None
    if row["eval_coverage"] is not None:
        eval_scores = EvaluationScores(
            coverage=row["eval_coverage"],
            faithfulness=row["eval_faithfulness"],
            hallucination_rate=row["eval_hallucination"],
            usefulness=row["eval_usefulness"],
            reasoning=row["eval_reasoning"] or "",
        )
    return JobResult(
        job_id=row["job_id"],
        status=JobStatus(row["status"]),
        question=row["question"],
        report=row["report"],
        error=row["error"],
        sources_count=row["sources_count"],
        evidence_count=row["evidence_count"],
        themes_count=row["themes_count"],
        evaluation=eval_scores,
    )


# ── Events ────────────────────────────────────────────────────────────────────

def db_append_event(job_id: str, event_type: str, data: dict[str, Any], ts: float) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO events (job_id, event_type, data, ts) VALUES (?,?,?,?)",
            (job_id, event_type, json.dumps(data), ts),
        )
        conn.commit()


def db_get_events(job_id: str, after: int = 0) -> list[dict[str, Any]]:
    """Return events after a given row offset (0-based)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT event_type, data, ts FROM events WHERE job_id = ? ORDER BY id LIMIT -1 OFFSET ?",
            (job_id, after),
        ).fetchall()
    return [{"type": r["event_type"], "data": json.loads(r["data"]), "timestamp": r["ts"]} for r in rows]


# ── States ────────────────────────────────────────────────────────────────────

def db_save_state(job_id: str, state: SharedState) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO states (job_id, body) VALUES (?,?)",
            (job_id, state.model_dump_json()),
        )
        conn.commit()


def db_get_state(job_id: str) -> SharedState | None:
    with _conn() as conn:
        row = conn.execute("SELECT body FROM states WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    return SharedState.model_validate_json(row["body"])
