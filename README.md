# ML-ESS: Multi-Agent Research Assistant

An end-to-end, multi-agent research system that autonomously searches, synthesizes, evaluates, and reports on complex research questions — built with FastAPI, Next.js, and state-of-the-art LLMs.


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
