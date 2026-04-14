# ML-ESS: Multi-Agent Research Assistant

An end-to-end, multi-agent research system that autonomously searches, synthesizes, evaluates, and reports on complex research questions — built with FastAPI, Next.js, and state-of-the-art LLMs.

---

## 🧠 How It Works

Each research question passes through **four sequential agents**:

```mermaid
flowchart LR
    Q([Research<br/> Question])
    S[Search<br/> Agent]
    SY[Synthesis<br/> Agent]
    R[Report<br/> Agent]
    E[Evaluator]
    O([Scored<br/> Report])

    Q --> S
    S --> SY
    SY --> R
    R --> E
    E --> O

    S:::stage
    SY:::stage
    R:::stage
    E:::stage

    classDef stage fill:#0d7c7c,color:#fff,stroke:none
ml-ess/
├── api/                        # Python backend
│   ├── main.py                 # Uvicorn entry point & CLI
│   ├── requirements.txt
│   ├── app/
│   │   ├── agents/
│   │   │   ├── search.py       # Stage 1 — query, fetch, extract evidence
│   │   │   ├── synthesis.py    # Stage 2 — themes & contradictions
│   │   │   ├── report.py       # Stage 3 — outline + full report
│   │   │   └── evaluator.py    # Stage 4 — quality scores
│   │   ├── core/
│   │   │   ├── pipeline.py     # Orchestrates the four agents
│   │   │   ├── llm.py          # chat() / chat_json() + Groq → HF fallback
│   │   │   ├── jobs.py         # Job manager, SSE event emitter
│   │   │   └── store.py        # SQLite WAL persistence
│   │   ├── api/
│   │   │   ├── routes.py       # FastAPI endpoints
│   │   │   ├── auth.py         # X-API-Key middleware
│   │   │   └── webhook.py      # Telegram / WhatsApp webhooks
│   │   └── models/
│   │       ├── state.py        # SharedState + sub-models (Pydantic v2)
│   │       └── api.py          # Request / response schemas
│   └── tests/
│       ├── test_agents.py
│       └── test_api.py
├── frontend/                   # Next.js 16 web UI
│   ├── app/                    # App Router pages & layouts
│   ├── components/             # ResearchForm, JobStatus, ReportView
│   ├── hooks/
│   │   └── useSSE.ts           # Server-Sent Events subscription hook
│   └── lib/
│       └── api.ts              # Typed fetch client
└── ressources/
    ├── report/latex/           # LaTeX technical report
    ├── slides/                 # Beamer presentation
    └── notebook/               # Jupyter walkthroughs
