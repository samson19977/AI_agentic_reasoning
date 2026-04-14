"""Shared LLM client — supports Groq and HuggingFace Inference API.

Provider selection via LLM_PROVIDER env var:
  - "groq"         → Groq only
  - "huggingface"  → HuggingFace only
  - "auto"         → try Groq first, fallback to HF on rate-limit / error
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Protocol

from app.core import config

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_RETRY_BACKOFF = (1, 2)  # seconds to wait before retrying on rate-limit / transient error


# ── Provider abstraction ────────────────────────────────────────────────────

class LLMClient(Protocol):
    """Minimal interface each provider must satisfy."""
    provider: str
    def completions(self, system: str, user: str) -> str: ...


def _is_rate_limit(exc: Exception) -> bool:
    """Check if an exception is a rate-limit / transient error."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", 0)
    return status in (429, 500, 502, 503, 504)


class GroqClient:
    """Wrapper around the Groq SDK with automatic fallback to a second API key."""
    provider = "groq"

    def __init__(self) -> None:
        from groq import Groq
        self._client = Groq(api_key=config.GROQ_API_KEY)
        self._client2 = Groq(api_key=config.GROQ_API_KEY_2) if config.GROQ_API_KEY_2 else None

    def _call(self, client, system: str, user: str) -> str:
        resp = client.chat.completions.create(
            model=config.GROQ_MODEL,
            temperature=config.TEMPERATURE,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    def completions(self, system: str, user: str) -> str:
        try:
            return self._call(self._client, system, user)
        except Exception as exc:
            if self._client2 is not None and _is_rate_limit(exc):
                logger.warning("Groq primary key failed (%s), trying fallback key…", exc)
                return self._call(self._client2, system, user)
            raise


class HuggingFaceClient:
    """Wrapper around HuggingFace Inference API (serverless)."""
    provider = "huggingface"

    def __init__(self) -> None:
        from huggingface_hub import InferenceClient
        self._client = InferenceClient(
            provider="auto",
            api_key=config.HF_TOKEN,
        )

    def completions(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=config.HF_MODEL,
            temperature=config.TEMPERATURE,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""


# ── Client factory ──────────────────────────────────────────────────────────

def _make_client(provider: str) -> LLMClient:
    if provider == "groq":
        return GroqClient()
    if provider == "huggingface":
        return HuggingFaceClient()
    raise ValueError(f"Unknown LLM provider: {provider}")


def get_client() -> LLMClient:
    """Return a configured LLM client based on LLM_PROVIDER setting."""
    provider = config.LLM_PROVIDER
    print(f"Configuring LLM client | provider={provider}")
    if provider == "auto":
        # Prefer Groq if key is set, otherwise HF
        if config.GROQ_API_KEY:
            return GroqClient()
        if config.HF_TOKEN:
            return HuggingFaceClient()
        raise RuntimeError("No LLM API key configured. Set GROQ_API_KEY or HF_TOKEN.")
    return _make_client(provider)


# ── Chat helpers (used by all agents) ───────────────────────────────────────

def chat(client: LLMClient, system: str, user: str) -> str:
    """Send a chat completion request with retries and optional provider fallback."""
    logger.debug("LLM request | provider=%s | system=%s...", client.provider, system[:80])
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES):
        try:
            content = client.completions(system, user)
            logger.debug("LLM response | provider=%s | length=%d", client.provider, len(content))
            return content
        except Exception as exc:
            last_exc = exc
            if _is_rate_limit(exc) and attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF[attempt]
                logger.warning(
                    "LLM call failed (provider=%s, attempt %d/%d, status %s), retrying in %ds…",
                    client.provider, attempt + 1, _MAX_RETRIES,
                    getattr(exc, "status_code", "?"), wait,
                )
                time.sleep(wait)
            else:
                break

    # ── Auto-fallback: try the other provider ────────────────────────────────
    if config.LLM_PROVIDER == "auto" and last_exc is not None:
        fallback_provider = "huggingface" if client.provider == "groq" else "groq"
        fallback_key = config.HF_TOKEN if fallback_provider == "huggingface" else config.GROQ_API_KEY
        if fallback_key:
            logger.warning(
                "Falling back from %s to %s after error: %s",
                client.provider, fallback_provider, last_exc,
            )
            try:
                fallback = _make_client(fallback_provider)
                content = fallback.completions(system, user)
                logger.info("Fallback to %s succeeded | length=%d", fallback_provider, len(content))
                return content
            except Exception as fb_exc:
                logger.error("Fallback to %s also failed: %s", fallback_provider, fb_exc)
                raise fb_exc from last_exc

    raise last_exc  # type: ignore[misc]


def extract_json(text: str) -> str:
    """Pull a JSON block out of an LLM response (fenced or raw)."""
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def chat_json(client: LLMClient, system: str, user: str) -> list | dict:
    """Send a chat request and parse the response as JSON.

    Returns an empty list on failure.
    """
    raw = chat(client, system, user)
    try:
        return json.loads(extract_json(raw))
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM JSON response: %s...", raw[:120])
        return []
