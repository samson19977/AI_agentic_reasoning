"""API request / response schemas."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel

from app.models.state import EvaluationScores


# ── Job status ───────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    PENDING = "pending"
    SEARCHING = "searching"
    SYNTHESISING = "synthesising"
    REPORTING = "reporting"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Request ──────────────────────────────────────────────────────────────────

class ResearchRequest(BaseModel):
    question: str


# ── Response ─────────────────────────────────────────────────────────────────

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    question: str


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    question: str
    report: str = ""
    evaluation: Optional[EvaluationScores] = None
    sources_count: int = 0
    evidence_count: int = 0
    themes_count: int = 0
    error: str = ""


# ── Webhook payloads ─────────────────────────────────────────────────────────

class WebhookEvent(BaseModel):
    """Generic inbound webhook payload."""
    source: str = "generic"
    sender_id: str = ""
    message: str = ""
    raw: dict = {}
