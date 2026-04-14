"""REST API routes for the research assistant."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import re

import markdown
import weasyprint
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse

from app.api.auth import require_api_key
from app.core.jobs import clear_all_jobs, create_job, delete_job, get_job, get_job_events, get_job_state, list_jobs
from app.models.api import JobResponse, JobResult, ResearchRequest

router = APIRouter(tags=["research"])

# Dependency shorthand applied to protected routes
_auth = Depends(require_api_key)

# Regex matching ```mermaid ... ``` fenced blocks
_MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)


def _mermaid_to_img_tags(md_text: str) -> str:
    """Replace Mermaid fenced code blocks with <img> tags for PDF rendering.

    Uses the mermaid.ink service to convert diagram code to images.
    """

    def _replace(match: re.Match) -> str:
        code = match.group(1).strip()
        encoded = base64.urlsafe_b64encode(code.encode()).decode()
        url = f"https://mermaid.ink/img/base64:{encoded}"
        return (
            f'<div style="text-align:center;margin:16px 0">'
            f'<img src="{url}" alt="diagram" style="max-width:100%">'
            f"</div>"
        )

    return _MERMAID_BLOCK_RE.sub(_replace, md_text)


@router.post("/research", response_model=JobResponse, status_code=202, dependencies=[_auth])
def submit_research(req: ResearchRequest):
    """Submit a research question. Returns a job ID immediately.

    The pipeline runs in the background. Poll GET /api/research/{job_id}
    for status and results.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    job = create_job(req.question.strip())
    return JobResponse(job_id=job.job_id, status=job.status, question=job.question)


@router.get("/research/{job_id}", response_model=JobResult, dependencies=[_auth])
def get_research(job_id: str):
    """Get the status and result of a research job."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.get("/research/{job_id}/reasoning", dependencies=[_auth])
def get_reasoning(job_id: str):
    """Get the full reasoning steps for a completed job.

    Returns sources, evidence, themes, contradictions, search queries,
    report outline, and evaluation reasoning.
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    state = get_job_state(job_id)
    if state is None:
        return {
            "job_id": job_id,
            "status": job.status,
            "available": False,
            "steps": [],
        }

    steps = []

    # 1. Search queries
    steps.append({
        "stage": "search",
        "title": "Search Queries",
        "description": f"Generated {len(state.search_queries)} search queries",
        "data": state.search_queries,
    })

    # 2. Sources discovered
    steps.append({
        "stage": "search",
        "title": "Sources Found",
        "description": f"Discovered {len(state.sources)} sources",
        "data": [s.model_dump() for s in state.sources],
    })

    # 3. Evidence extracted
    steps.append({
        "stage": "search",
        "title": "Evidence Extracted",
        "description": f"Extracted {len(state.evidence)} pieces of evidence",
        "data": [e.model_dump() for e in state.evidence],
    })

    # 4. Themes identified
    steps.append({
        "stage": "synthesis",
        "title": "Themes Identified",
        "description": f"Identified {len(state.themes)} themes",
        "data": [t.model_dump() for t in state.themes],
    })

    # 5. Contradictions detected
    if state.contradictions:
        steps.append({
            "stage": "synthesis",
            "title": "Contradictions Detected",
            "description": f"Found {len(state.contradictions)} contradictions",
            "data": [c.model_dump() for c in state.contradictions],
        })

    # 6. Report outline
    if state.report_outline:
        steps.append({
            "stage": "report",
            "title": "Report Outline",
            "description": f"Planned {len(state.report_outline)} sections",
            "data": state.report_outline,
        })

    # 7. Evaluation reasoning
    if state.evaluation and state.evaluation.reasoning:
        steps.append({
            "stage": "evaluation",
            "title": "Evaluation Reasoning",
            "description": "Quality assessment rationale",
            "data": state.evaluation.reasoning,
        })

    return {
        "job_id": job_id,
        "status": job.status,
        "available": True,
        "steps": steps,
    }


@router.get("/research/{job_id}/pdf", dependencies=[_auth])
def download_pdf(job_id: str):
    """Download the research report as a PDF."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if not job.report:
        raise HTTPException(status_code=409, detail="Report not ready yet.")

    # Convert Mermaid blocks to <img> tags before Markdown rendering
    report_md = _mermaid_to_img_tags(job.report)

    html_body = markdown.markdown(
        report_md,
        extensions=["extra", "codehilite", "toc"],
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 2cm; }}
  body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
         font-size: 11pt; line-height: 1.6; color: #1a1a1a; }}
  h1 {{ font-size: 20pt; margin-top: 0; color: #111; }}
  h2 {{ font-size: 15pt; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
  h3 {{ font-size: 12pt; }}
  code {{ background: #f5f5f5; padding: 1px 4px; border-radius: 3px; font-size: 10pt; }}
  pre {{ background: #f5f5f5; padding: 12px; border-radius: 4px;
         overflow-x: auto; font-size: 9pt; }}
  blockquote {{ border-left: 3px solid #ccc; margin-left: 0; padding-left: 12px;
               color: #555; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
  th {{ background: #f0f0f0; }}
  img {{ max-width: 100%; height: auto; }}
  /* References: wrap long URLs and keep each entry on its own line */
  h2#references ~ p, h2#references ~ ol, h2#references ~ ul,
  h3#references ~ p, h3#references ~ ol, h3#references ~ ul {{
    word-break: break-all;
    overflow-wrap: break-word;
  }}
  /* Catch plain-paragraph reference lists (no list element) */
  p {{ word-break: break-word; overflow-wrap: break-word; }}
</style>
</head><body>
<h1>{job.question}</h1>
<hr>
{html_body}
</body></html>"""

    pdf_bytes = weasyprint.HTML(string=html).write_pdf()

    slug = re.sub(r"[^a-zA-Z0-9 _-]", "", job.question[:50]).strip().replace(" ", "_")
    filename = f"{slug}_report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/research", response_model=list[JobResult], dependencies=[_auth])
def list_research():
    """List all research jobs."""
    return list_jobs()


@router.delete("/research", status_code=200, dependencies=[_auth])
def clear_research():
    """Delete all research jobs and their data."""
    count = clear_all_jobs()
    return {"deleted": count}


@router.delete("/research/{job_id}", status_code=200, dependencies=[_auth])
def delete_research(job_id: str):
    """Delete a single research job and its data."""
    found = delete_job(job_id)
    if not found:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"deleted": job_id}


@router.get("/research/{job_id}/events", dependencies=[_auth])
async def stream_events(job_id: str):
    """Stream reasoning events for a job via Server-Sent Events.

    The client subscribes and receives structured events as they happen.
    The stream closes when the job completes or fails.
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    async def event_generator():
        cursor = 0
        while True:
            events = get_job_events(job_id, after=cursor)
            for event in events:
                yield f"data: {json.dumps(event)}\n\n"
                cursor += 1
                if event["type"] in ("job_completed", "job_failed"):
                    return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# @router.get("/health")
@router.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}
