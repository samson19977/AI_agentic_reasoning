"""Pipeline — orchestrates the multi-agent research workflow."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from app.agents import search, synthesis, report, evaluator
from app.models.api import JobStatus
from app.models.state import SharedState

logger = logging.getLogger(__name__)


def run_pipeline(
    question: str,
    output_dir: str | None = "output",
    on_stage: Optional[Callable[[JobStatus], None]] = None,
    on_event: Optional[Callable[[str, dict[str, Any] | None], None]] = None,
    language: str = "English",
) -> SharedState:
    """Run the full research pipeline for a given question.

    Stages:
        1. SearchAgent   — discover sources, extract evidence
        2. SynthesisAgent — organise evidence into themes
        3. ReportAgent    — generate structured report
        4. Evaluator      — score report quality

    Returns the final SharedState.
    """
    state = SharedState(research_question=question, language=language)
    logger.info("Pipeline started | question=%s", question)

    if on_event:
        on_event("pipeline_started", {"question": question})

    if on_stage:
        on_stage(JobStatus.SEARCHING)
    state = search.run(state, on_event=on_event)

    if on_stage:
        on_stage(JobStatus.SYNTHESISING)
    state = synthesis.run(state, on_event=on_event)

    if on_stage:
        on_stage(JobStatus.REPORTING)
    state = report.run(state, on_event=on_event)

    if on_stage:
        on_stage(JobStatus.EVALUATING)
    state = evaluator.run(state, on_event=on_event)

    state.completed_at = datetime.now(timezone.utc).isoformat()

    # Optionally save to disk
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        slug = "".join(
            c if c.isalnum() or c in " -_" else "" for c in question[:50]
        ).strip().replace(" ", "_")

        report_path = out / f"{slug}_report.md"
        report_path.write_text(state.final_report, encoding="utf-8")

        state_path = out / f"{slug}_state.json"
        state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")

        logger.info("Outputs saved to %s", out)

    logger.info("Pipeline completed | %s", state.summary())
    return state
