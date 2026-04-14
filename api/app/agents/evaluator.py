"""Evaluator — scores the final report on a defined rubric."""

from __future__ import annotations

import logging
import textwrap

from app.core.llm import get_client, chat_json
from app.models.state import EvaluationScores, SharedState

logger = logging.getLogger(__name__)


def run(state: SharedState, on_event=None) -> SharedState:
    logger.info("Evaluator: starting...")
    client = get_client()

    if on_event:
        on_event("stage_started", {"stage": "evaluation"})

    if not state.final_report:
        logger.warning("No report to evaluate.")
        return state

    evidence_summary = "\n".join(
        f"[{i}] {ev.claim} (source: {state.sources[ev.source_index].title if ev.source_index < len(state.sources) else 'unknown'})"
        for i, ev in enumerate(state.evidence)
    )

    system = textwrap.dedent("""\
        You are a research quality evaluator. You are given:
        1. A research question
        2. The evidence that was available to the report writer
        3. The final report

        Score the report on four dimensions (each 0.0 to 1.0):
        - coverage: Does the report address the key parts of the question?
        - faithfulness: Are the claims in the report supported by the evidence provided?
        - hallucination_rate: What proportion of claims appear unsupported or overstated?
          (0.0 = no hallucination, 1.0 = entirely hallucinated)
        - usefulness: Is the report clear, relevant, and useful for decision-making?

        Return a JSON object:
        {
          "coverage": 0.85,
          "faithfulness": 0.9,
          "hallucination_rate": 0.1,
          "usefulness": 0.8,
          "reasoning": "Brief explanation of scores"
        }
        Return ONLY the JSON object.
    """)
    user = (
        f"Research question: {state.research_question}\n\n"
        f"Available evidence:\n{evidence_summary}\n\n"
        f"Final report:\n{state.final_report}"
    )
    scores = chat_json(client, system, user)
    if isinstance(scores, dict):
        try:
            state.evaluation = EvaluationScores(
                coverage=float(scores.get("coverage", 0)),
                faithfulness=float(scores.get("faithfulness", 0)),
                hallucination_rate=float(scores.get("hallucination_rate", 0)),
                usefulness=float(scores.get("usefulness", 0)),
                reasoning=scores.get("reasoning", ""),
            )
            logger.info(
                "Scores: coverage=%.2f faithfulness=%.2f hallucination=%.2f usefulness=%.2f",
                state.evaluation.coverage,
                state.evaluation.faithfulness,
                state.evaluation.hallucination_rate,
                state.evaluation.usefulness,
            )
            if on_event:
                on_event("evaluation_completed", {
                    "coverage": state.evaluation.coverage,
                    "faithfulness": state.evaluation.faithfulness,
                    "hallucination_rate": state.evaluation.hallucination_rate,
                    "usefulness": state.evaluation.usefulness,
                    "reasoning": state.evaluation.reasoning,
                })
        except (ValueError, TypeError) as exc:
            logger.warning("Could not parse evaluation scores: %s", exc)
    else:
        logger.warning("Evaluator returned non-dict response")

    return state
