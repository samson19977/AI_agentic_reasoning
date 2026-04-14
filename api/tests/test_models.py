"""Tests for Pydantic models in app.models.state and app.models.api."""

from app.models.state import (
    Confidence,
    Contradiction,
    Evidence,
    EvaluationScores,
    SharedState,
    Source,
    Theme,
)
from app.models.api import JobResult, JobStatus, ResearchRequest, WebhookEvent


# ── State models ─────────────────────────────────────────────────────────────

class TestSource:
    def test_defaults(self):
        s = Source(title="Test", url="https://example.com")
        assert s.title == "Test"
        assert s.snippet == ""
        assert s.accessed_at  # auto-set

    def test_full(self):
        s = Source(title="T", url="https://x.com", snippet="data", credibility_notes="good")
        assert s.credibility_notes == "good"


class TestEvidence:
    def test_minimal(self):
        ev = Evidence(claim="AI is useful", source_index=0)
        assert ev.claim == "AI is useful"
        assert ev.quote == ""


class TestTheme:
    def test_defaults(self):
        t = Theme(name="Performance", summary="About speed")
        assert t.confidence == Confidence.MEDIUM
        assert t.evidence_indices == []


class TestEvaluationScores:
    def test_bounds(self):
        scores = EvaluationScores(
            coverage=0.9,
            faithfulness=0.85,
            hallucination_rate=0.1,
            usefulness=0.8,
        )
        assert 0 <= scores.coverage <= 1
        assert scores.reasoning == ""


class TestSharedState:
    def test_empty_state(self):
        state = SharedState(research_question="What is AI?")
        assert state.sources == []
        assert state.evidence == []
        assert state.themes == []
        assert state.evaluation is None

    def test_summary(self):
        state = SharedState(research_question="Test question")
        summary = state.summary()
        assert "Test question" in summary
        assert "Sources:" in summary


# ── API models ───────────────────────────────────────────────────────────────

class TestResearchRequest:
    def test_from_dict(self):
        req = ResearchRequest(question="What is ML?")
        assert req.question == "What is ML?"


class TestJobResult:
    def test_defaults(self):
        job = JobResult(
            job_id="abc123",
            status=JobStatus.PENDING,
            question="Test",
        )
        assert job.report == ""
        assert job.sources_count == 0

    def test_completed(self):
        job = JobResult(
            job_id="abc123",
            status=JobStatus.COMPLETED,
            question="Q",
            report="# Report",
            sources_count=5,
            evidence_count=10,
            themes_count=3,
        )
        assert job.status == JobStatus.COMPLETED


class TestWebhookEvent:
    def test_defaults(self):
        event = WebhookEvent(message="Hello")
        assert event.source == "generic"
        assert event.sender_id == ""
