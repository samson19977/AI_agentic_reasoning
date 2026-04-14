"""SynthesisAgent — organises evidence into themes and identifies contradictions."""

from __future__ import annotations

import logging
import textwrap

from app.core.llm import get_client, chat_json
from app.models.state import Confidence, Contradiction, SharedState, Theme

logger = logging.getLogger(__name__)


def _format_evidence(state: SharedState) -> str:
    lines: list[str] = []
    for i, ev in enumerate(state.evidence):
        src = state.sources[ev.source_index] if ev.source_index < len(state.sources) else None
        src_label = src.title if src else "unknown source"
        lines.append(
            f"[{i}] Claim: {ev.claim}\n"
            f"    Quote: {ev.quote}\n"
            f"    Source: {src_label}\n"
            f"    Relevance: {ev.relevance}"
        )
    return "\n\n".join(lines)


def _identify_themes(client, state: SharedState) -> list[Theme]:
    system = textwrap.dedent("""\
        You are a research synthesis expert. You are given a research question
        and a numbered list of evidence fragments. Group them into coherent
        themes. Each theme should capture a distinct aspect of the answer.

        Return a JSON array of theme objects:
        [
          {
            "name": "Theme title",
            "summary": "2-3 sentence summary of this theme",
            "evidence_indices": [0, 3, 7],
            "confidence": "high" | "medium" | "low"
          }
        ]
        Return ONLY the JSON array.
    """)
    user = (
        f"Research question: {state.research_question}\n\n"
        f"Evidence:\n{_format_evidence(state)}"
    )
    items = chat_json(client, system, user)
    if not isinstance(items, list):
        return []

    return [
        Theme(
            name=item.get("name", ""),
            summary=item.get("summary", ""),
            evidence_indices=item.get("evidence_indices", []),
            confidence=Confidence(item.get("confidence", "medium")),
        )
        for item in items
        if isinstance(item, dict) and "name" in item
    ]


def _identify_contradictions(client, state: SharedState) -> list[Contradiction]:
    system = textwrap.dedent("""\
        You are a research analyst. You are given a research question and
        a numbered list of evidence fragments. Identify any contradictions,
        disagreements, or tensions between pieces of evidence.

        Return a JSON array of contradiction objects:
        [
          {
            "description": "What the disagreement is about",
            "evidence_indices": [2, 5],
            "resolution": "How the contradiction might be explained or reconciled"
          }
        ]
        If there are no contradictions, return an empty array [].
        Return ONLY the JSON array.
    """)
    user = (
        f"Research question: {state.research_question}\n\n"
        f"Evidence:\n{_format_evidence(state)}"
    )
    items = chat_json(client, system, user)
    if not isinstance(items, list):
        return []

    return [
        Contradiction(
            description=item.get("description", ""),
            evidence_indices=item.get("evidence_indices", []),
            resolution=item.get("resolution", ""),
        )
        for item in items
        if isinstance(item, dict) and "description" in item
    ]


def run(state: SharedState, on_event=None) -> SharedState:
    logger.info("SynthesisAgent: starting...")
    client = get_client()

    if on_event:
        on_event("stage_started", {"stage": "synthesis"})

    if not state.evidence:
        logger.warning("No evidence to synthesise.")
        return state

    state.themes = _identify_themes(client, state)
    logger.info("Identified %d themes", len(state.themes))
    if on_event:
        on_event("themes_identified", {
            "count": len(state.themes),
            "themes": [{"name": t.name, "summary": t.summary, "confidence": t.confidence.value} for t in state.themes],
        })

    state.contradictions = _identify_contradictions(client, state)
    logger.info("Found %d contradictions", len(state.contradictions))
    if on_event:
        on_event("contradictions_identified", {
            "count": len(state.contradictions),
            "contradictions": [{"description": c.description, "resolution": c.resolution} for c in state.contradictions],
        })

    return state
