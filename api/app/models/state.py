"""Pydantic models for the research pipeline shared state."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────

class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ── Source & Evidence ────────────────────────────────────────────────────────

class Source(BaseModel):
    title: str
    url: str
    accessed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    credibility_notes: str = ""
    snippet: str = ""
    images: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    claim: str
    source_index: int
    quote: str = ""
    relevance: str = ""


# ── Synthesis ────────────────────────────────────────────────────────────────

class Theme(BaseModel):
    name: str
    summary: str
    evidence_indices: list[int] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class Contradiction(BaseModel):
    description: str
    evidence_indices: list[int] = Field(default_factory=list)
    resolution: str = ""


# ── Evaluation ───────────────────────────────────────────────────────────────

class EvaluationScores(BaseModel):
    coverage: float = Field(0.0, ge=0, le=1)
    faithfulness: float = Field(0.0, ge=0, le=1)
    hallucination_rate: float = Field(0.0, ge=0, le=1)
    usefulness: float = Field(0.0, ge=0, le=1)
    reasoning: str = ""


# ── Shared State ─────────────────────────────────────────────────────────────

class SharedState(BaseModel):
    research_question: str = ""
    language: str = "English"

    # SearchAgent
    search_queries: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)

    # SynthesisAgent
    themes: list[Theme] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)

    # ReportAgent
    report_outline: list[str] = Field(default_factory=list)
    final_report: str = ""

    # Evaluation
    evaluation: Optional[EvaluationScores] = None

    # Metadata
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""

    def summary(self) -> str:
        lines = [
            f"Research Question: {self.research_question}",
            f"Search Queries:    {len(self.search_queries)}",
            f"Sources:           {len(self.sources)}",
            f"Evidence:          {len(self.evidence)}",
            f"Themes:            {len(self.themes)}",
            f"Contradictions:    {len(self.contradictions)}",
            f"Report length:     {len(self.final_report)} chars",
            f"Evaluated:         {self.evaluation is not None}",
        ]
        return "\n".join(lines)
