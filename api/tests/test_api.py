"""Tests for the FastAPI REST API endpoints."""

from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from app.api.app import app
from app.models.api import JobResult, JobStatus

client = TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestResearchEndpoints:
    @patch("app.api.routes.create_job")
    def test_submit_research_returns_202(self, mock_create):
        mock_create.return_value = JobResult(
            job_id="test123",
            status=JobStatus.PENDING,
            question="What is ML?",
        )
        resp = client.post("/api/research", json={"question": "What is ML?"})
        assert resp.status_code == 202
        data = resp.json()
        assert data["job_id"] == "test123"
        assert data["status"] == "pending"

    def test_submit_empty_question_returns_400(self):
        resp = client.post("/api/research", json={"question": "   "})
        assert resp.status_code == 400

    @patch("app.api.routes.get_job")
    def test_get_research_returns_job(self, mock_get):
        mock_get.return_value = JobResult(
            job_id="test123",
            status=JobStatus.COMPLETED,
            question="Q",
            report="# Done",
        )
        resp = client.get("/api/research/test123")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    @patch("app.api.routes.get_job")
    def test_get_unknown_job_returns_404(self, mock_get):
        mock_get.return_value = None
        resp = client.get("/api/research/nonexistent")
        assert resp.status_code == 404

    @patch("app.api.routes.list_jobs")
    def test_list_research_returns_list(self, mock_list):
        mock_list.return_value = []
        resp = client.get("/api/research")
        assert resp.status_code == 200
        assert resp.json() == []


class TestWebhookEndpoints:
    @patch("app.api.webhook.config")
    def test_whatsapp_verify_success(self, mock_config):
        mock_config.WHATSAPP_VERIFY_TOKEN = "test-token"
        resp = client.get(
            "/webhook/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test-token",
                "hub.challenge": "12345",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == 12345

    @patch("app.api.webhook.config")
    def test_whatsapp_verify_fails_bad_token(self, mock_config):
        mock_config.WHATSAPP_VERIFY_TOKEN = "correct"
        resp = client.get(
            "/webhook/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "12345",
            },
        )
        assert resp.status_code == 403

    @patch("app.api.webhook._send_whatsapp_message")
    @patch("app.api.webhook.create_job")
    @patch("app.api.webhook.config")
    def test_whatsapp_inbound_creates_job_with_callbacks(
        self, mock_config, mock_create, mock_send
    ):
        mock_config.WEBHOOK_SECRET = ""
        mock_config.WHATSAPP_TOKEN = "tok"
        mock_config.WHATSAPP_PHONE_ID = "123"
        mock_create.return_value = JobResult(
            job_id="wa001",
            status=JobStatus.PENDING,
            question="Test Q",
        )
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "33612345678",
                                        "type": "text",
                                        "text": {"body": "Test Q"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        resp = client.post("/webhook/whatsapp", json=payload)
        assert resp.status_code == 200
        assert resp.json()["job_id"] == "wa001"
        # Verify create_job was called with callbacks
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs[0][0] == "Test Q"
        assert call_kwargs[1]["on_progress"] is not None
        assert call_kwargs[1]["on_complete"] is not None
        # Verify acknowledgement was sent
        mock_send.assert_called_once()
        assert "33612345678" == mock_send.call_args[0][0]

    @patch("app.api.webhook._send_whatsapp_message")
    @patch("app.api.webhook.config")
    def test_whatsapp_inbound_ignores_non_text(self, mock_config, mock_send):
        mock_config.WEBHOOK_SECRET = ""
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {"from": "33600000000", "type": "image"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        resp = client.post("/webhook/whatsapp", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
        mock_send.assert_not_called()

    @patch("app.api.webhook.create_job")
    def test_generic_webhook_creates_job(self, mock_create):
        mock_create.return_value = JobResult(
            job_id="wh001",
            status=JobStatus.PENDING,
            question="Webhook Q",
        )
        resp = client.post(
            "/webhook/inbound",
            json={"message": "Webhook Q", "source": "slack"},
        )
        assert resp.status_code == 200
        assert resp.json()["job_id"] == "wh001"

    def test_generic_webhook_rejects_empty_message(self):
        resp = client.post(
            "/webhook/inbound",
            json={"message": "   "},
        )
        assert resp.status_code == 400


class TestWhatsAppHelpers:
    @patch("app.api.webhook._send_whatsapp_message")
    def test_chunked_short_message_sends_once(self, mock_send):
        from app.api.webhook import _send_whatsapp_chunked

        _send_whatsapp_chunked("33600000000", "Short message")
        mock_send.assert_called_once_with("33600000000", "Short message")

    @patch("app.api.webhook._send_whatsapp_message")
    def test_chunked_long_message_splits(self, mock_send):
        from app.api.webhook import _send_whatsapp_chunked, _WA_MAX_LEN

        # Build a message that needs splitting: two big paragraphs
        para1 = "A" * 3000
        para2 = "B" * 3000
        text = f"{para1}\n\n{para2}"
        _send_whatsapp_chunked("33600000000", text)
        assert mock_send.call_count == 2
        # Each chunk should have a [1/2] or [2/2] header
        first_call = mock_send.call_args_list[0][0][1]
        second_call = mock_send.call_args_list[1][0][1]
        assert "[1/2]" in first_call
        assert "[2/2]" in second_call

    @patch("app.api.webhook._send_whatsapp_message")
    def test_complete_callback_sends_report(self, mock_send):
        from app.api.webhook import _make_complete_callback
        from app.models.state import EvaluationScores

        callback = _make_complete_callback("33600000000")
        job = JobResult(
            job_id="j1",
            status=JobStatus.COMPLETED,
            question="Q",
            report="# My Report\n\nSome content here.",
            evaluation=EvaluationScores(
                coverage=0.9,
                faithfulness=0.85,
                hallucination_rate=0.1,
                usefulness=0.95,
            ),
            sources_count=5,
            evidence_count=10,
            themes_count=3,
        )
        callback("j1", job)
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][1]
        assert "Research complete" in sent_text
        assert "My Report" in sent_text
        assert "90%" in sent_text  # coverage

    @patch("app.api.webhook._send_whatsapp_message")
    def test_complete_callback_sends_error(self, mock_send):
        from app.api.webhook import _make_complete_callback

        callback = _make_complete_callback("33600000000")
        job = JobResult(
            job_id="j2",
            status=JobStatus.FAILED,
            question="Q",
            error="LLM timeout",
        )
        callback("j2", job)
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][1]
        assert "failed" in sent_text.lower()
        assert "LLM timeout" in sent_text

    @patch("app.api.webhook._send_whatsapp_message")
    def test_progress_callback_sends_stage_updates(self, mock_send):
        from app.api.webhook import _make_progress_callback

        callback = _make_progress_callback("33600000000")
        callback("j1", JobStatus.SEARCHING)
        callback("j1", JobStatus.SYNTHESISING)
        callback("j1", JobStatus.REPORTING)
        callback("j1", JobStatus.EVALUATING)
        assert mock_send.call_count == 4

    @patch("app.api.webhook._send_whatsapp_message")
    def test_progress_callback_skips_completed(self, mock_send):
        from app.api.webhook import _make_progress_callback

        callback = _make_progress_callback("33600000000")
        callback("j1", JobStatus.COMPLETED)
        callback("j1", JobStatus.FAILED)
        mock_send.assert_not_called()


class TestReasoningEndpoint:
    @patch("app.api.routes.get_job_state")
    @patch("app.api.routes.get_job")
    def test_reasoning_returns_steps(self, mock_get, mock_state):
        from app.models.state import SharedState, Source, Evidence, Theme, Confidence

        state = SharedState(research_question="Q")
        state.search_queries = ["q1", "q2"]
        state.sources = [Source(title="S1", url="http://s1.com", snippet="...")]
        state.evidence = [Evidence(claim="C1", source_index=0, quote="Q1", relevance="R1")]
        state.themes = [Theme(name="T1", summary="S1", evidence_indices=[0], confidence=Confidence.HIGH)]

        mock_get.return_value = JobResult(job_id="r1", status=JobStatus.COMPLETED, question="Q")
        mock_state.return_value = state

        resp = client.get("/api/research/r1/reasoning")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert len(data["steps"]) >= 3  # queries, sources, evidence, themes

    @patch("app.api.routes.get_job")
    def test_reasoning_not_found(self, mock_get):
        mock_get.return_value = None
        resp = client.get("/api/research/none/reasoning")
        assert resp.status_code == 404


class TestSSEEventsEndpoint:
    @patch("app.api.routes.get_job")
    @patch("app.api.routes.get_job_events")
    def test_events_stream(self, mock_events, mock_get):
        mock_get.return_value = JobResult(job_id="e1", status=JobStatus.COMPLETED, question="Q")
        mock_events.return_value = [
            {"type": "stage_started", "data": {"stage": "search"}, "timestamp": 1.0},
            {"type": "job_completed", "data": {}, "timestamp": 2.0},
        ]

        resp = client.get("/api/research/e1/events")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        lines = resp.text.strip().split("\n\n")
        assert len(lines) >= 2

    @patch("app.api.routes.get_job")
    def test_events_not_found(self, mock_get):
        mock_get.return_value = None
        resp = client.get("/api/research/none/events")
        assert resp.status_code == 404


class TestAuthentication:
    """API key authentication tests.

    We temporarily patch config.API_KEY to simulate a server with auth enabled.
    """

    @patch("app.api.auth.config")
    def test_missing_key_returns_401(self, mock_cfg):
        mock_cfg.API_KEY = "secret-key"
        resp = client.post("/api/research", json={"question": "Q"})
        assert resp.status_code == 401

    @patch("app.api.auth.config")
    def test_wrong_key_returns_403(self, mock_cfg):
        mock_cfg.API_KEY = "secret-key"
        resp = client.post(
            "/api/research",
            json={"question": "Q"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 403

    @patch("app.api.routes.create_job")
    @patch("app.api.auth.config")
    def test_correct_key_returns_202(self, mock_cfg, mock_create):
        mock_cfg.API_KEY = "secret-key"
        mock_create.return_value = JobResult(
            job_id="auth01", status=JobStatus.PENDING, question="Q"
        )
        resp = client.post(
            "/api/research",
            json={"question": "Q"},
            headers={"X-API-Key": "secret-key"},
        )
        assert resp.status_code == 202

    @patch("app.api.auth.config")
    def test_empty_key_config_allows_all(self, mock_cfg):
        """When API_KEY is not set, all requests pass through (dev mode)."""
        mock_cfg.API_KEY = ""
        resp = client.post("/api/research", json={"question": "   "})
        # Still gets 400 because question is blank — not 401
        assert resp.status_code == 400

    def test_health_requires_no_key(self):
        """Health endpoint is always open."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
