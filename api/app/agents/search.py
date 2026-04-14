"""SearchAgent — finds sources and extracts evidence for a research question."""

from __future__ import annotations

import logging
import textwrap
import time

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

from app.core import config
from app.core.llm import get_client, chat, chat_json
from app.models.state import Evidence, SharedState, Source

logger = logging.getLogger(__name__)

# Lazy Tavily client — created once on first use (only if key is set).
_tavily_client = None


def _get_tavily_client():
    """Return a TavilyClient if the API key is configured, else None."""
    global _tavily_client
    if _tavily_client is not None:
        return _tavily_client
    if not config.TAVILY_API_KEY:
        return None
    try:
        from tavily import TavilyClient
        _tavily_client = TavilyClient(api_key=config.TAVILY_API_KEY)
        return _tavily_client
    except Exception as exc:
        logger.warning("Failed to initialise Tavily client: %s", exc)
        return None


# ── Web helpers ──────────────────────────────────────────────────────────────

# Minimum dimensions (in attribute value) to consider an image meaningful.
_MIN_IMG_DIMENSION = 150


def _fetch_page(url: str) -> tuple[str, list[str]]:
    """Fetch a URL and return (cleaned body text, list of image URLs)."""
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as http:
            resp = http.get(url, headers={"User-Agent": "ResearchAssistant/1.0"})
            resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # ── Extract meaningful images before stripping tags ──────────────
        images: list[str] = []
        for img in soup.find_all("img", src=True):
            src = img["src"]
            # Skip tiny icons, tracking pixels, data URIs, and SVG sprites
            if src.startswith("data:") or "/icon" in src.lower() or ".svg" in src.lower():
                continue
            # Check explicit width/height attributes to skip tiny images
            w = img.get("width", "")
            h = img.get("height", "")
            try:
                if w and int(w) < _MIN_IMG_DIMENSION:
                    continue
                if h and int(h) < _MIN_IMG_DIMENSION:
                    continue
            except ValueError:
                pass
            # Resolve relative URLs
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                from urllib.parse import urljoin
                src = urljoin(url, src)
            if src.startswith("http"):
                images.append(src)

        # Deduplicate while preserving order, keep first 10
        seen: set[str] = set()
        unique_images: list[str] = []
        for img_url in images:
            if img_url not in seen:
                seen.add(img_url)
                unique_images.append(img_url)
            if len(unique_images) >= 10:
                break

        # ── Extract text ────────────────────────────────────────────────
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[: config.MAX_CONTENT_LENGTH], unique_images
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        return "", []


def _search_tavily(query: str, max_results: int = config.MAX_RESULTS_PER_QUERY) -> list[dict]:
    """Run a Tavily search and normalise results to the same shape as DDG."""
    client = _get_tavily_client()
    if client is None:
        return []
    try:
        response = client.search(
            query=query,
            max_results=max_results,
            include_raw_content=True,
            include_images=True,
        )
        results = []
        # Collect top-level images returned by Tavily
        top_images = response.get("images", []) or []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "href": r.get("url", ""),
                "body": r.get("content", ""),
                "raw_content": r.get("raw_content", ""),
                "images": top_images,
            })
        return results
    except Exception as exc:
        logger.warning("Tavily search failed for '%s': %s", query, exc)
        return []


def _search_ddg(query: str, max_results: int = config.MAX_RESULTS_PER_QUERY) -> list[dict]:
    """Run a DuckDuckGo search and return result dicts (with retry)."""
    for attempt in range(3):
        try:
            results = list(DDGS().text(query, max_results=max_results))
            if results:
                return results
            logger.warning("Empty DDG results for '%s' (attempt %d/3)", query, attempt + 1)
            time.sleep(1.0 * (attempt + 1))
        except Exception as exc:
            logger.warning("DDG search failed for '%s' (attempt %d/3): %s", query, attempt + 1, exc)
            time.sleep(1.0 * (attempt + 1))
    return []


def _search_web(query: str, max_results: int = config.MAX_RESULTS_PER_QUERY) -> list[dict]:
    """Search via Tavily first; fall back to DuckDuckGo on failure."""
    results = _search_tavily(query, max_results)
    if results:
        return results
    logger.info("Tavily returned no results for '%s', falling back to DuckDuckGo", query)
    return _search_ddg(query, max_results)


# ── Core logic ───────────────────────────────────────────────────────────────

def _generate_queries(client, question: str) -> list[str]:
    system = textwrap.dedent("""\
        You are a research assistant. Given a research question, generate a JSON
        list of concise web-search queries (strings) that would help find
        diverse, high-quality sources. Return ONLY a JSON array of strings.
    """)
    user = f"Research question: {question}\n\nGenerate {config.MAX_SEARCH_QUERIES} search queries."
    result = chat_json(client, system, user)
    if isinstance(result, list) and result:
        return [str(q) for q in result[: config.MAX_SEARCH_QUERIES]]
    return [question]


def _extract_evidence(client, question: str, source: Source) -> list[Evidence]:
    if not source.snippet:
        return []

    system = textwrap.dedent("""\
        You are a research evidence extractor. Given a research question and
        source text, extract important claims, facts, or arguments that are
        relevant to the question.

        Return a JSON array of objects, each with:
          - "claim": a concise statement of the claim/fact
          - "quote": a short direct quote supporting the claim
          - "relevance": why this matters for the research question

        Return ONLY the JSON array.
    """)
    user = (
        f"Research question: {question}\n\n"
        f"Source: {source.title} ({source.url})\n\n"
        f"Content:\n{source.snippet}"
    )
    items = chat_json(client, system, user)
    if not isinstance(items, list):
        return []

    return [
        Evidence(
            claim=item.get("claim", ""),
            source_index=-1,
            quote=item.get("quote", ""),
            relevance=item.get("relevance", ""),
        )
        for item in items
        if isinstance(item, dict) and "claim" in item
    ]


# ── Public entry point ───────────────────────────────────────────────────────

def run(state: SharedState, on_event=None) -> SharedState:
    """Execute the SearchAgent stage: discover sources and extract evidence."""
    logger.info("SearchAgent: starting...")
    client = get_client()

    if on_event:
        on_event("stage_started", {"stage": "search"})

    # 1. Generate search queries
    state.search_queries = _generate_queries(client, state.research_question)
    logger.info("Generated %d search queries", len(state.search_queries))
    if on_event:
        on_event("search_queries_generated", {"queries": state.search_queries})

    # 2. Search the web
    seen_urls: set[str] = set()
    for query in state.search_queries:
        logger.info("Searching: %s", query)
        for r in _search_web(query):
            url = r.get("href", r.get("link", ""))
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            # Tavily may provide raw_content — prefer it over snippet
            content = r.get("raw_content") or r.get("body", "")
            state.sources.append(
                Source(
                    title=r.get("title", ""),
                    url=url,
                    snippet=content,
                    images=r.get("images", []),
                )
            )
    logger.info("Found %d unique sources", len(state.sources))
    if on_event:
        on_event("sources_found", {
            "count": len(state.sources),
            "sources": [{"title": s.title, "url": s.url} for s in state.sources[:10]],
        })

    # 3. Fetch full content and extract evidence
    for i, source in enumerate(state.sources):
        logger.info("Fetching [%d/%d]: %s", i + 1, len(state.sources), source.title[:60])
        page_text, page_images = _fetch_page(source.url)
        if page_text:
            source.snippet = page_text
        # Merge scraped images with any images from search results
        if page_images:
            seen_imgs = set(source.images)
            for img in page_images:
                if img not in seen_imgs:
                    source.images.append(img)
                    seen_imgs.add(img)

        evidence = _extract_evidence(client, state.research_question, source)
        for ev in evidence:
            ev.source_index = i
        state.evidence.extend(evidence)

    logger.info("Extracted %d evidence fragments", len(state.evidence))
    if on_event:
        on_event("evidence_extracted", {
            "count": len(state.evidence),
            "samples": [e.claim for e in state.evidence[:5]],
        })
    return state
