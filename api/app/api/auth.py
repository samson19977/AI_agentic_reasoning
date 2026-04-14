"""API key authentication dependency.

All protected routes require the header:
    X-API-Key: <your key>

Set API_KEY in .env. If API_KEY is empty the server starts but logs a
warning — useful for local development without a key.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.core import config

logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Security(_api_key_header)) -> str:
    """FastAPI dependency — raises 401 if the key is missing or wrong."""
    configured = config.API_KEY

    # Dev mode: no key configured → allow all traffic (warn once)
    if not configured:
        return "dev-mode"

    if not key:
        raise HTTPException(status_code=401, detail="X-API-Key header is required.")

    # Constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(key, configured):
        raise HTTPException(status_code=403, detail="Invalid API key.")

    return key
