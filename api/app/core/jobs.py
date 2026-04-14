"""Job store and background worker for async research jobs.

Persistence is handled by app.core.store (SQLite).
The in-memory _events dict is kept as a write-through cache so SSE streams
can read events without hitting SQLite on every poll tick.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from typing import Any, Callable, Dict, List, Optional

from app.core.pipeline import run_pipeline
from app.core.store import (
    db_append_event,
    db_clear_all_jobs,
    db_delete_job,
    db_get_events,
    db_get_job,
    db_get_state,
    db_list_jobs,
    db_save_state,
    db_upsert_job,
)
from app.models.api import JobResult, JobStatus
from app.models.state import SharedState

logger = logging.getLogger(__name__)

# Type alias for callbacks
ProgressCallback = Callable[[str, JobStatus], None]
CompleteCallback = Callable[[str, JobResult], None]

# Write-through in-memory cache (avoids per-poll DB reads for SSE streams).
# The DB is the source of truth; this cache is rebuilt from DB on cold start
# only for jobs that are still running (there shouldn't be any after restart,
# so this is effectively just a hot-path optimisation for the current process).
_jobs_cache: Dict[str, JobResult] = {}
# Events are append-only so we only need the count per job for the offset.
_event_counts: Dict[str, int] = {}


# ── Public API ────────────────────────────────────────────────────────────────

def append_job_event(job_id: str, event_type: str, data: dict[str, Any] | None = None) -> None:
    """Persist a reasoning event and update the local count cache."""
    ts = time.time()
    db_append_event(job_id, event_type, data or {}, ts)
    _event_counts[job_id] = _event_counts.get(job_id, 0) + 1


def get_job_events(job_id: str, after: int = 0) -> list[dict[str, Any]]:
    """Return events for a job starting after `after` (0-based offset)."""
    return db_get_events(job_id, after=after)


def create_job(
    question: str,
    on_progress: Optional[ProgressCallback] = None,
    on_complete: Optional[CompleteCallback] = None,
    language: str = "English",
) -> JobResult:
    """Create a new research job, persist it, and start a background thread."""
    job_id = uuid.uuid4().hex[:12]
    job = JobResult(job_id=job_id, status=JobStatus.PENDING, question=question)
    db_upsert_job(job)
    _jobs_cache[job_id] = job

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, question, on_progress, on_complete, language),
        daemon=True,
    )
    thread.start()
    logger.info("Job %s created for: %s", job_id, question[:80])
    return job


def get_job(job_id: str) -> JobResult | None:
    """Return a job, checking the cache first then falling back to DB."""
    if job_id in _jobs_cache:
        return _jobs_cache[job_id]
    job = db_get_job(job_id)
    if job:
        _jobs_cache[job_id] = job
    return job


def get_job_state(job_id: str) -> SharedState | None:
    """Return the full pipeline state for a completed job."""
    return db_get_state(job_id)


def list_jobs() -> list[JobResult]:
    """List all jobs (most recent first) from DB."""
    return db_list_jobs()


def delete_job(job_id: str) -> bool:
    """Delete a single job and its data. Returns True if the job existed."""
    _jobs_cache.pop(job_id, None)
    _event_counts.pop(job_id, None)
    return db_delete_job(job_id)


def clear_all_jobs() -> int:
    """Delete all jobs and their data. Returns the number deleted."""
    _jobs_cache.clear()
    _event_counts.clear()
    return db_clear_all_jobs()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _set_status(
    job: JobResult,
    job_id: str,
    status: JobStatus,
    on_progress: Optional[ProgressCallback],
) -> None:
    job.status = status
    db_upsert_job(job)
    if on_progress:
        try:
            on_progress(job_id, status)
        except Exception:
            logger.exception("Progress callback failed for job %s", job_id)


def _run_job(
    job_id: str,
    question: str,
    on_progress: Optional[ProgressCallback],
    on_complete: Optional[CompleteCallback],
    language: str = "English",
) -> None:
    """Execute the pipeline in a background thread and persist all state."""
    job = _jobs_cache[job_id]

    def on_event(event_type: str, data: dict[str, Any] | None = None) -> None:
        append_job_event(job_id, event_type, data)

    try:
        append_job_event(job_id, "job_created", {"question": question})
        _set_status(job, job_id, JobStatus.SEARCHING, on_progress)
        state = run_pipeline(
            question,
            output_dir=f"output/{job_id}",
            on_stage=lambda stage: _set_status(job, job_id, stage, on_progress),
            on_event=on_event,
            language=language,
        )

        job.report = state.final_report
        job.evaluation = state.evaluation
        job.sources_count = len(state.sources)
        job.evidence_count = len(state.evidence)
        job.themes_count = len(state.themes)

        db_save_state(job_id, state)
        _set_status(job, job_id, JobStatus.COMPLETED, on_progress)
        append_job_event(job_id, "job_completed")
        logger.info("Job %s completed", job_id)

    except Exception as exc:
        job.error = str(exc)
        _set_status(job, job_id, JobStatus.FAILED, on_progress)
        append_job_event(job_id, "job_failed", {"error": str(exc)})
        logger.error("Job %s failed: %s\n%s", job_id, exc, traceback.format_exc())

    finally:
        if on_complete:
            try:
                on_complete(job_id, _jobs_cache[job_id])
            except Exception:
                logger.exception("Complete callback failed for job %s", job_id)
