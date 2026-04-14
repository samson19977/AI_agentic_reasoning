"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.webhook import router as webhook_router
from app.core import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Multi-Agent Research Assistant",
        description="API for submitting research questions and retrieving evidence-backed reports.",
        version="1.0.0",
    )

 
    _CORS_ORIGINS = [origin.strip() for origin in config.CORS_ORIGINS.split(",") if origin.strip()]
    print(f"Allowed CORS origins: {_CORS_ORIGINS}")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")
    app.include_router(webhook_router, prefix="/webhook")

    return app


app = create_app()
