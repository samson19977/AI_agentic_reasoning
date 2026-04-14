"""ReportAgent — produces a structured, evidence-backed research report."""

from __future__ import annotations

import logging
import textwrap

from app.core.llm import get_client, chat, chat_json
from app.models.state import SharedState

logger = logging.getLogger(__name__)


def _build_context(state: SharedState) -> str:
    sections: list[str] = []

    # ── Deduplicate sources by URL ───────────────────────────────────────────
    # Build a mapping: original source index → deduplicated source number
    url_to_dedup: dict[str, int] = {}
    dedup_sources: list = []
    orig_to_dedup: dict[int, int] = {}

    for i, src in enumerate(state.sources):
        if src.url not in url_to_dedup:
            dedup_idx = len(dedup_sources)
            url_to_dedup[src.url] = dedup_idx
            dedup_sources.append(src)
        orig_to_dedup[i] = url_to_dedup[src.url]

    # Helper to translate evidence indices to deduplicated source numbers
    def _evidence_source_refs(evidence_indices: list[int]) -> str:
        src_nums = sorted({
            orig_to_dedup.get(state.evidence[ei].source_index, 0)
            for ei in evidence_indices
            if ei < len(state.evidence)
        })
        return ", ".join(str(n) for n in src_nums)

    sections.append("## Themes")
    for i, t in enumerate(state.themes):
        refs = _evidence_source_refs(t.evidence_indices)
        sections.append(
            f"### Theme {i+1}: {t.name} (confidence: {t.confidence.value})\n"
            f"{t.summary}\n"
            f"Sources: [{refs}]"
        )

    if state.contradictions:
        sections.append("\n## Contradictions")
        for c in state.contradictions:
            refs = _evidence_source_refs(c.evidence_indices)
            sections.append(
                f"- {c.description} (sources: [{refs}])\n"
                f"  Resolution: {c.resolution}"
            )

    sections.append("\n## Evidence")
    for i, ev in enumerate(state.evidence):
        src_num = orig_to_dedup.get(ev.source_index, 0)
        src = dedup_sources[src_num] if src_num < len(dedup_sources) else None
        src_label = f"[{src_num}] {src.title}" if src else "unknown"
        sections.append(
            f"- {ev.claim}\n"
            f"    Quote: \"{ev.quote}\"\n"
            f"    Source: {src_label}"
        )

    sections.append("\n## Sources")
    for i, src in enumerate(dedup_sources):
        line = f"[{i}] {src.title} — {src.url} (accessed {src.accessed_at})"
        if src.images:
            img_list = "  ".join(src.images[:5])
            line += f"\n    Images: {img_list}"
        sections.append(line)

    return "\n".join(sections)


def _generate_outline(client, state: SharedState) -> list[str]:
    system = textwrap.dedent("""\
        You are a report planner. Given a research question and synthesised
        themes, produce a clear outline for a research report.

        Return a JSON array of section heading strings. A good outline
        typically includes: Title, Introduction, one section per major theme,
        Discussion (agreements/disagreements), Limitations, Conclusion,
        and References.

        Return ONLY the JSON array.
    """)
    theme_summary = "\n".join(f"- {t.name}: {t.summary}" for t in state.themes)
    user = f"Research question: {state.research_question}\n\nThemes:\n{theme_summary}"
    result = chat_json(client, system, user)
    if isinstance(result, list) and result:
        return [str(s) for s in result]
    return ["Introduction", "Findings", "Discussion", "Limitations", "Conclusion", "References"]


def _write_report(client, state: SharedState) -> str:
    system = textwrap.dedent(f"""\
        You are an academic research report writer. Write a well-structured
        research report in Markdown following the outline provided.
        IMPORTANT: Write the ENTIRE report in {state.language}. Every heading,
        sentence, and reference entry must be in {state.language}.

        Requirements:
        - Every major claim MUST cite its source using the numbered references
          from the Sources list, e.g. [1], [2]. Each number maps to a unique
          URL — do NOT duplicate references. Only use source numbers that
          appear in the provided Sources list.
        - The References section at the end must list each source ONCE.
          CRITICAL: each reference must be on its own separate line with a
          blank line between entries. Use exactly this format:

          [1] Title of first source. https://url-of-first-source.com

          [2] Title of second source. https://url-of-second-source.com

          [3] Title of third source. https://url-of-third-source.com

          NEVER put multiple references on the same line.
          Do not repeat the same source under different numbers.
        - Include a Limitations section acknowledging gaps and uncertainties.
        - Where sources disagree, present both perspectives fairly.
        - Do NOT invent claims beyond the evidence provided.
        - Use formal, clear academic language.
        - The report should be thorough but concise (aim for 1500-2500 words).
        - Some sources include image URLs. When an image is directly relevant
          to the discussion (e.g. architecture diagrams, result charts,
          comparison tables), embed it in the report using Markdown syntax:
          ![description](image_url)
          Only include images that genuinely illustrate a point. Do not embed
          every available image — pick the 2-5 most informative ones.
        - Where it adds value, include Mermaid diagrams to illustrate
          relationships, processes, comparisons, or taxonomies. Use fenced
          code blocks with the language tag "mermaid", for example:

          ```mermaid
          flowchart LR
            A[Input] --> B[Process] --> C[Output]
          ```

          Good uses: concept maps linking themes, flowcharts of processes,
          comparison tables (as flowcharts), and timelines. Only include a
          diagram when it genuinely clarifies the content — do not force one
          into every section. Aim for 1-3 diagrams total.
    """)
    user = (
        f"Research question: {state.research_question}\n\n"
        f"Report outline:\n" + "\n".join(f"- {s}" for s in state.report_outline) + "\n\n"
        f"Context:\n{_build_context(state)}"
    )
    return chat(client, system, user)


# ── Output normalisation ─────────────────────────────────────────────────────

import re as _re

_REF_INLINE_RE = _re.compile(
    r'(\[\d+\][^\[]+?)(?=\[\d+\])',
)


def _normalise_references(report: str) -> str:
    """Ensure every reference entry is on its own line.

    The LLM sometimes produces references run together on one line:
      [1] First ref. URL [2] Second ref. URL
    This splits them so each [n] starts on a new line.
    """
    # Find the References section
    marker = _re.search(r'^#{1,3}\s*References', report, _re.MULTILINE)
    if not marker:
        return report

    body = report[: marker.start()]
    refs_section = report[marker.start() :]

    # Split inline refs: insert a newline before each [n] that follows text
    refs_section = _re.sub(r'(?<=\S)(\s*)(\[\d+\])', r'\n\n\2', refs_section)

    # Collapse 3+ blank lines down to 2
    refs_section = _re.sub(r'\n{3,}', '\n\n', refs_section)

    return body + refs_section


def run(state: SharedState, on_event=None) -> SharedState:
    logger.info("ReportAgent: starting...")
    client = get_client()

    if on_event:
        on_event("stage_started", {"stage": "report"})

    if not state.themes:
        logger.warning("No themes to report on.")
        return state

    state.report_outline = _generate_outline(client, state)
    logger.info("Outline: %s", state.report_outline)
    if on_event:
        on_event("report_outline_generated", {"outline": state.report_outline})

    state.final_report = _normalise_references(_write_report(client, state))
    logger.info("Report generated (%d chars)", len(state.final_report))
    if on_event:
        on_event("report_generated", {"length": len(state.final_report), "preview": state.final_report[:500]})

    return state
