"""Tests for each agent — LLM calls are mocked."""

from unittest.mock import MagicMock, patch
import json

from app.models.state import (
    Confidence,
    Evidence,
    EvaluationScores,
    SharedState,
    Source,
    Theme,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_state(**kwargs) -> SharedState:
    defaults = dict(research_question="What is AI?")
    defaults.update(kwargs)
    return SharedState(**defaults)


def _mock_groq_response(content: str) -> MagicMock:
    """Build a mock that looks like a Groq ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── SearchAgent ──────────────────────────────────────────────────────────────

class TestSearchAgent:
    @patch("app.agents.search.get_client")
    @patch("app.agents.search._search_web")
    @patch("app.agents.search._fetch_page_text")
    @patch("app.agents.search.chat_json")
    def test_run_populates_sources_and_evidence(
        self, mock_chat_json, mock_fetch, mock_search, mock_get_client
    ):
        mock_get_client.return_value = MagicMock()
        # chat_json returns search queries, then evidence per source
        mock_chat_json.side_effect = [
            ["AI definition", "AI applications"],  # queries
            [{"claim": "AI is...", "quote": "AI def", "relevance": "core"}],  # evidence for source 1
            [{"claim": "ML is...", "quote": "ML helps", "relevance": "related"}],  # evidence for source 2
        ]
        mock_search.return_value = [
            {"title": "Src 1", "href": "https://a.com", "body": "body1"},
            {"title": "Src 2", "href": "https://b.com", "body": "body2"},
        ]
        mock_fetch.return_value = "full page content"

        from app.agents.search import run

        state = run(_make_state())

        assert len(state.sources) >= 2
        assert len(state.evidence) >= 2
        assert state.evidence[0].claim == "AI is..."

    @patch("app.agents.search.get_client")
    @patch("app.agents.search._search_web")
    @patch("app.agents.search.chat_json")
    def test_run_handles_no_results(self, mock_chat_json, mock_search, mock_get_client):
        mock_get_client.return_value = MagicMock()
        mock_chat_json.return_value = ["query 1"]
        mock_search.return_value = []

        from app.agents.search import run

        state = run(_make_state())
        assert state.sources == []
        assert state.evidence == []


# ── SynthesisAgent ───────────────────────────────────────────────────────────

class TestSynthesisAgent:
    @patch("app.agents.synthesis.get_client")
    @patch("app.agents.synthesis.chat_json")
    def test_run_identifies_themes_and_contradictions(self, mock_chat_json, mock_get_client):
        mock_get_client.return_value = MagicMock()
        mock_chat_json.side_effect = [
            # themes
            [
                {
                    "name": "Performance",
                    "summary": "CNNs vs Transformers",
                    "evidence_indices": [0],
                    "confidence": "high",
                }
            ],
            # contradictions
            [
                {
                    "description": "Conflicting results",
                    "evidence_indices": [0, 1],
                    "resolution": "Different datasets",
                }
            ],
        ]

        state = _make_state(
            sources=[Source(title="S1", url="https://a.com")],
            evidence=[
                Evidence(claim="CNNs are faster", source_index=0),
                Evidence(claim="Transformers are faster", source_index=0),
            ],
        )

        from app.agents.synthesis import run

        state = run(state)

        assert len(state.themes) == 1
        assert state.themes[0].name == "Performance"
        assert state.themes[0].confidence == Confidence.HIGH
        assert len(state.contradictions) == 1

    @patch("app.agents.synthesis.get_client")
    def test_run_with_no_evidence(self, mock_get_client):
        mock_get_client.return_value = MagicMock()

        from app.agents.synthesis import run

        state = run(_make_state())
        assert state.themes == []
        assert state.contradictions == []


# ── ReportAgent ──────────────────────────────────────────────────────────────

class TestReportAgent:
    @patch("app.agents.report.get_client")
    @patch("app.agents.report.chat_json")
    @patch("app.agents.report.chat")
    def test_run_generates_report(self, mock_chat, mock_chat_json, mock_get_client):
        mock_get_client.return_value = MagicMock()
        mock_chat_json.return_value = ["Introduction", "Analysis", "Conclusion"]
        mock_chat.return_value = "# Report\n\nThis is a test report."

        state = _make_state(
            sources=[Source(title="S1", url="https://a.com")],
            evidence=[Evidence(claim="Test claim", source_index=0)],
            themes=[Theme(name="T1", summary="Summary", evidence_indices=[0])],
        )

        from app.agents.report import run

        state = run(state)

        assert state.report_outline == ["Introduction", "Analysis", "Conclusion"]
        assert "Report" in state.final_report

    @patch("app.agents.report.get_client")
    def test_run_with_no_themes(self, mock_get_client):
        mock_get_client.return_value = MagicMock()

        from app.agents.report import run

        state = run(_make_state())
        assert state.final_report == ""


# ── Evaluator ────────────────────────────────────────────────────────────────

class TestEvaluator:
    @patch("app.agents.evaluator.get_client")
    @patch("app.agents.evaluator.chat_json")
    def test_run_scores_report(self, mock_chat_json, mock_get_client):
        mock_get_client.return_value = MagicMock()
        mock_chat_json.return_value = {
            "coverage": 0.9,
            "faithfulness": 0.85,
            "hallucination_rate": 0.05,
            "usefulness": 0.8,
            "reasoning": "Good report",
        }

        state = _make_state(
            sources=[Source(title="S1", url="https://a.com")],
            evidence=[Evidence(claim="Claim A", source_index=0)],
            final_report="# Full Report\nContent here.",
        )

        from app.agents.evaluator import run

        state = run(state)

        assert state.evaluation is not None
        assert state.evaluation.coverage == 0.9
        assert state.evaluation.hallucination_rate == 0.05

    @patch("app.agents.evaluator.get_client")
    def test_run_with_no_report(self, mock_get_client):
        mock_get_client.return_value = MagicMock()

        from app.agents.evaluator import run

        state = run(_make_state())
        assert state.evaluation is None
