---
title: "AIMS RIC - Doctoral Training School:Multi-Agent AI Research Assistant"
format:
  pdf:
    toc: true
    number-sections: true
    colorlinks: true
---


# AIMS RIC - Doctoral Training School:Multi-Agent AI Research Assistant
### Technical Report — April 2026


## Abstract

ML-ESS is a full-stack AI system that automates end-to-end research: given a natural language question, it orchestrates four specialized AI agents to search the web, synthesize evidence, draft a structured report, and evaluate the report's quality. The system exposes a REST API (FastAPI) and a modern web interface (Next.js), supporting real-time progress tracking, PDF export, and multi-provider LLM fallback.

---

## 1. Introduction & Motivation

Conducting thorough research manually is time-consuming: it involves querying multiple sources, extracting relevant claims, resolving contradictions, and composing a coherent, well-cited document. ML-ESS automates this entire workflow through a multi-agent pipeline, replacing hours of manual work with a structured, reproducible process.

**Core objectives:**

- Accept any research question in natural language
- Autonomously gather evidence from the open web
- Synthesize findings into themes, resolving contradictions
- Generate a structured Markdown report with citations and diagrams
- Score the report's quality along four dimensions
- Deliver everything through a clean web UI with real-time feedback

---

## 2. System Architecture

### 2.1 High-Level Overview

The system is divided into two main services: a Python backend responsible for all AI reasoning and data persistence, and a Next.js frontend that provides the user interface.

```mermaid
graph TB
    subgraph Frontend["Frontend — Next.js :3000"]
        UI["Web UI\n(React 19 + Tailwind)"]
    end

    subgraph Backend["Backend — FastAPI :8000"]
        API["REST API\n/api/research"]
        Pipeline["Multi-Agent Pipeline"]
        Jobs["Job Manager\n(Background Threads)"]
        DB["SQLite Database\n(WAL mode)"]

        subgraph Agents["Agents"]
            A1["Search Agent"]
            A2["Synthesis Agent"]
            A3["Report Agent"]
            A4["Evaluator"]
        end

        subgraph LLMs["LLM Providers"]
            Groq["Groq\nllama-3.3-70b"]
            HF["HuggingFace\nLlama-3.3-70B"]
        end
    end

    UI <-->|"HTTP / SSE"| API
    API --> Jobs
    Jobs --> Pipeline
    Pipeline --> A1 --> A2 --> A3 --> A4
    Agents <-->|"chat() with retry + fallback"| Groq
    Groq -.->|"rate-limit fallback"| HF
    Jobs <--> DB
```

### 2.2 Backend Directory Structure

```
api/
├── main.py                  ← CLI & server entry point
├── app/
│   ├── agents/
│   │   ├── search.py        ← Web search & evidence extraction
│   │   ├── synthesis.py     ← Theme identification & contradiction detection
│   │   ├── report.py        ← Outline creation & Markdown generation
│   │   └── evaluator.py     ← Quality scoring
│   ├── api/
│   │   ├── app.py           ← FastAPI app factory, CORS, routers
│   │   ├── routes.py        ← REST endpoints & SSE streaming
│   │   ├── auth.py          ← API key authentication
│   │   └── webhook.py       ← WhatsApp integration (optional)
│   ├── core/
│   │   ├── pipeline.py      ← Sequential agent orchestration
│   │   ├── jobs.py          ← Background thread management & caching
│   │   ├── store.py         ← SQLite persistence (WAL mode)
│   │   ├── llm.py           ← LLM client with retries & fallback
│   │   └── config.py        ← Environment variable loading
│   └── models/
│       ├── api.py           ← Request/response Pydantic schemas
│       └── state.py         ← Pipeline shared state schema
└── tests/                   ← Pytest test suite
```

### 2.3 Request Lifecycle & Data Flow

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant API as FastAPI
    participant Jobs as Job Manager
    participant Pipeline as Pipeline
    participant DB as SQLite

    User->>FE: Enter research question
    FE->>API: POST /api/research
    API->>Jobs: create_job(question)
    Jobs->>DB: INSERT job (status=pending)
    Jobs-->>API: job_id
    API-->>FE: 202 job_id

    Jobs->>Pipeline: run_pipeline() [background thread]

    loop Poll every 2 seconds
        FE->>API: GET /api/research/id
        API->>DB: SELECT job
        DB-->>API: job row
        API-->>FE: status, progress
    end

    Pipeline->>DB: UPDATE status=searching
    Note over Pipeline: Search Agent runs
    Pipeline->>DB: UPDATE status=synthesising
    Note over Pipeline: Synthesis Agent runs
    Pipeline->>DB: UPDATE status=reporting
    Note over Pipeline: Report Agent runs
    Pipeline->>DB: UPDATE status=evaluating
    Note over Pipeline: Evaluator runs
    Pipeline->>DB: UPDATE status=completed, report=...

    FE->>API: GET /api/research/id
    API-->>FE: status=completed, report, evaluation
    FE-->>User: Display report + scores
```

---

## 3. The Multi-Agent Pipeline

Each agent in the pipeline is a stateless function that reads from and writes to a shared `SharedState` object. Agents are called sequentially — each one enriches the state for the next.

### 3.1 SharedState Schema

```mermaid
classDiagram
    class SharedState {
        +str research_question
        +list search_queries
        +list sources
        +list evidence
        +list themes
        +list contradictions
        +list report_outline
        +str final_report
        +EvaluationScores evaluation
        +str started_at
        +str completed_at
    }

    class Source {
        +str title
        +str url
        +str snippet
        +list images
        +str credibility_notes
        +str accessed_at
    }

    class Evidence {
        +str claim
        +int source_index
        +str quote
        +float relevance
    }

    class Theme {
        +str name
        +str summary
        +list evidence_indices
        +Confidence confidence
    }

    class Contradiction {
        +str description
        +list evidence_indices
        +str resolution
    }

    class EvaluationScores {
        +float coverage
        +float faithfulness
        +float hallucination_rate
        +float usefulness
        +str reasoning
    }

    class Confidence {
        <<enumeration>>
        high
        medium
        low
    }

    SharedState "1" --> "0..*" Source
    SharedState "1" --> "0..*" Evidence
    SharedState "1" --> "0..*" Theme
    SharedState "1" --> "0..*" Contradiction
    SharedState "1" --> "0..1" EvaluationScores
    Theme --> Confidence
```

### 3.2 Agent Pipeline Flow

```mermaid
flowchart TD
    Q([Research Question]) --> S1

    subgraph S1["Search Agent"]
        direction TB
        s1a["LLM: Generate 3 search queries"]
        s1b["DDG / Tavily search\n3–5 results per query"]
        s1c["httpx: Fetch pages\nBeautifulSoup: parse text + images"]
        s1d["LLM: Extract claims, quotes, relevance"]
        s1a --> s1b --> s1c --> s1d
    end

    subgraph S2["Synthesis Agent"]
        direction TB
        s2a["LLM: Group evidence into themes\n(with confidence levels)"]
        s2b["LLM: Detect contradictions\nbetween evidence pieces"]
        s2a --> s2b
    end

    subgraph S3["Report Agent"]
        direction TB
        s3a["LLM: Create section outline"]
        s3b["LLM: Write full Markdown report\n~2000–2500 words"]
        s3c["Embed citations and images"]
        s3a --> s3b --> s3c
    end

    subgraph S4["Evaluator Agent"]
        direction TB
        s4a["LLM: Score report vs evidence"]
        s4b["Output: coverage, faithfulness,\nhallucination_rate, usefulness"]
        s4a --> s4b
    end

    S1 --> S2 --> S3 --> S4
    S4 --> OUT([SharedState — complete])
```

### 3.3 Search Agent Detail

```mermaid
flowchart LR
    Q["Research Question"] --> GQ["LLM\nGenerate queries"]

    GQ --> Q1["query 1"]
    GQ --> Q2["query 2"]
    GQ --> Q3["query 3"]

    Q1 & Q2 & Q3 --> SE{Search Engine}

    SE -->|primary| DDG["DuckDuckGo\nfree, no key"]
    SE -->|if TAVILY_API_KEY| TAV["Tavily\npremium, richer content"]

    DDG & TAV --> URLs["Deduplicated URLs\n(up to 15)"]

    URLs --> FETCH["httpx GET\ntimeout=10s"]
    FETCH --> PARSE["BeautifulSoup4\nExtract text + images"]
    PARSE --> TRUNC["Truncate to\nMAX_CONTENT_LENGTH chars"]
    TRUNC --> LLM2["LLM\nExtract Evidence"]

    LLM2 --> EV["list[Evidence]\nclaim, quote, relevance, source_index"]
    EV --> STATE["SharedState\n.sources + .evidence"]
```

### 3.4 LLM Provider Strategy

```mermaid
flowchart TD
    CFG["LLM_PROVIDER env var"] --> AUTO{auto?}

    AUTO -->|groq| GC["GroqClient\nllama-3.3-70b-versatile"]
    AUTO -->|huggingface| HFC["HuggingFaceClient\nmeta-llama/Llama-3.3-70B-Instruct"]
    AUTO -->|auto| CHECK{GROQ_API_KEY set?}

    CHECK -->|yes| GC
    CHECK -->|no| HFC

    GC --> CALL["chat() — send prompt"]
    HFC --> CALL

    CALL --> ERR{Error?}
    ERR -->|success| OUT["Response text"]
    ERR -->|429/5xx, attempt lt 3| WAIT["Wait 1s / 3s\nRetry"]
    WAIT --> CALL
    ERR -->|primary key rate-limited| KEY2{GROQ_API_KEY_2 available?}
    KEY2 -->|yes| GC2["Retry with\nsecondary Groq key"]
    KEY2 -->|no| FB{LLM_PROVIDER == auto?}
    FB -->|yes| FBP["Fallback to\nalternate provider"]
    FBP --> CALL
    FB -->|no| RAISE["Raise exception"]

    GC2 --> CALL
    OUT --> JSON["chat_json()\nJSON extraction +\nparsing"]
```

### 3.5 Evaluation Scores

| Dimension | Score |
|-----------|-------|
| Coverage | 0.87 |
| Faithfulness | 0.92 |
| Usefulness | 0.85 |
| Hallucination Rate | 0.08 |

---

## 4. Data Persistence

### 4.1 SQLite Schema

```mermaid
erDiagram
    JOBS {
        TEXT job_id PK
        TEXT question
        TEXT status
        TEXT report
        TEXT evaluation
        INTEGER sources_count
        INTEGER evidence_count
        INTEGER themes_count
        TEXT created_at
        TEXT completed_at
        TEXT error
    }

    STATES {
        TEXT job_id FK
        TEXT state
    }

    EVENTS {
        INTEGER id PK
        TEXT job_id FK
        TEXT type
        TEXT data
        TEXT created_at
    }

    JOBS ||--o| STATES : "has full state"
    JOBS ||--o{ EVENTS : "emits events"
```

### 4.2 Job Status Lifecycle

```mermaid
stateDiagram-v2
    [*] --> pending : POST /api/research

    pending --> searching : Search Agent starts
    searching --> synthesising : Evidence extracted
    synthesising --> reporting : Themes identified
    reporting --> evaluating : Report written
    evaluating --> completed : Scores assigned

    searching --> failed : Exception
    synthesising --> failed : Exception
    reporting --> failed : Exception
    evaluating --> failed : Exception

    completed --> [*]
    failed --> [*]
```

### 4.3 SSE Event Stream

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as FastAPI (SSE)
    participant EV as Events Table

    FE->>API: GET /api/research/id/events
    Note over API,EV: Streams events as they are appended

    API-->>FE: event: stage_change — searching
    API-->>FE: event: queries_ready — queries list
    API-->>FE: event: sources_ready — count 12
    API-->>FE: event: stage_change — synthesising
    API-->>FE: event: themes_ready — count 5
    API-->>FE: event: stage_change — reporting
    API-->>FE: event: stage_change — evaluating
    API-->>FE: event: job_completed — job_id
    Note over FE: Stream closes on terminal event
```

---

## 5. REST API Reference

All endpoints except `/api/health` require the header `X-API-Key: <key>` when `API_KEY` is configured.

| Method | Endpoint | Status | Description |
|--------|----------|--------|-------------|
| `POST` | `/api/research` | 202 | Submit a research question |
| `GET` | `/api/research` | 200 | List all jobs |
| `GET` | `/api/research/{id}` | 200 | Get job status, report, and scores |
| `GET` | `/api/research/{id}/reasoning` | 200 | Detailed reasoning steps |
| `GET` | `/api/research/{id}/events` | 200 | SSE live event stream |
| `GET` | `/api/research/{id}/pdf` | 200 | Download report as styled PDF |
| `DELETE` | `/api/research/{id}` | 200 | Delete a single job |
| `DELETE` | `/api/research` | 200 | Delete all jobs |
| `GET` | `/api/health` | 200 | Health check (no auth) |

---

## 6. Frontend Application

The Next.js 16 frontend (React 19, Tailwind CSS 4, TypeScript) provides three pages.

### 6.1 Page & Component Tree

```mermaid
graph TD
    subgraph Pages
        HOME["/\nHome Page"]
        HIST["/history\nJob History"]
        JOB["/job/[id]\nJob Detail"]
    end

    subgraph HomeComponents["Home Page Components"]
        SF["SubmitForm"]
        MB["MessageBubble (per job)"]
        SS["StatusStepper"]
        SC["ScoreCard"]
        RV["ReportView"]
        RP["ReasoningPanel"]
        PL["useJobPoller hook\n(polls every 2s)"]
    end

    subgraph HistComponents["History Page Components"]
        JT["Job Table\n(all jobs)"]
        SB["StatusBadge"]
        DEL["Delete buttons"]
    end

    subgraph JobComponents["Job Detail Components"]
        JH["Job Header\n(id, question, status)"]
        SS2["StatusStepper"]
        SC2["ScoreCard"]
        AB["Action Bar\n(download MD / PDF)"]
        RP2["ReasoningPanel"]
        RV2["ReportView"]
    end

    HOME --> SF
    HOME --> MB
    MB --> SS
    MB --> SC
    MB --> RV
    MB --> RP
    MB --> PL

    HIST --> JT
    JT --> SB
    JT --> DEL

    JOB --> JH
    JOB --> SS2
    JOB --> SC2
    JOB --> AB
    JOB --> RP2
    JOB --> RV2
```

### 6.2 Frontend Data Flow

```mermaid
flowchart LR
    ENV["NEXT_PUBLIC_API_URL\nNEXT_PUBLIC_API_KEY"] --> LIB["lib/api.ts\nTyped fetch wrappers"]

    LIB --> submitResearch
    LIB --> getJob
    LIB --> listJobs
    LIB --> deleteJob
    LIB --> downloadPdf

    submitResearch --> POLL["useJobPoller(id)\nsetInterval 2000ms"]
    POLL -->|terminal state| STOP["Stop polling\n(completed / failed)"]

    getJob --> JobResult["JobResult\nstatus, report,\nevaluation, counts"]
    JobResult --> RV["ReportView\nMarkdown renderer\n+ mermaid diagrams"]
    JobResult --> SC["ScoreCard\n4 score bars"]
    JobResult --> SS["StatusStepper\n6-stage progress"]
```

---

## 7. Technology Stack Summary

| Layer | Technology | Version | Role |
|-------|-----------|---------|------|
| Backend language | Python | 3.11+ | All agent and API logic |
| API framework | FastAPI | ≥0.115 | HTTP server, routing, validation |
| ASGI server | Uvicorn | ≥0.30 | Production server |
| LLM (primary) | Groq SDK | ≥0.1 | `llama-3.3-70b-versatile` |
| LLM (fallback) | HuggingFace Hub | ≥0.25 | `Llama-3.3-70B-Instruct` |
| Web search | ddgs | ≥9.0 | DuckDuckGo search (no key) |
| Web search (opt.) | tavily-python | ≥0.5 | Premium search API |
| Web scraping | httpx + bs4 | latest | Page fetching and parsing |
| Data validation | Pydantic | ≥2.0 | Schemas, serialization |
| Database | SQLite | built-in | Persistence, WAL mode |
| PDF generation | WeasyPrint | ≥62.0 | Markdown → styled PDF |
| Markdown | markdown | ≥3.0 | HTML conversion for PDF |
| Config | python-dotenv | ≥1.0 | `.env` loading |
| Frontend | Next.js | 16.2.1 | React 19 App Router |
| Styling | Tailwind CSS | v4 | Utility-first CSS |
| Language (FE) | TypeScript | latest | Type safety |
| Deployment (FE) | Vercel | — | Hosted frontend |

---

## 8. Configuration

Key environment variables (set in `api/.env`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_PROVIDER` | `auto` | `groq`, `huggingface`, or `auto` |
| `GROQ_API_KEY` | — | Primary Groq API key |
| `GROQ_API_KEY_2` | — | Fallback Groq key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model |
| `HF_TOKEN` | — | HuggingFace token |
| `TEMPERATURE` | `0.3` | LLM sampling temperature |
| `TAVILY_API_KEY` | — | Optional premium search |
| `MAX_SEARCH_QUERIES` | `3` | Queries generated per question |
| `MAX_RESULTS_PER_QUERY` | `5` | Web results fetched per query |
| `MAX_CONTENT_LENGTH` | `3000` | Max characters scraped per page |
| `API_KEY` | — | Auth key (empty = no auth in dev) |
| `DB_PATH` | `data/jobs.db` | SQLite file location |
| `CORS_ORIGINS` | Vercel URL | Allowed frontend origins |

---

## 9. Deployment Architecture

### 9.1 Current vs. Scalable Architecture

```mermaid
graph TB
    subgraph Current["Current — Single Instance"]
        direction LR
        FE1["Vercel\n(Frontend)"] -->|HTTPS| API1["FastAPI\n(single process)"]
        API1 --> TH["threading.Thread\n(per job)"]
        TH --> SQ["SQLite\n(WAL mode)"]
        API1 --> SQ
    end

    subgraph Scaled["Production Scale — Horizontal"]
        direction LR
        FE2["Vercel\n(Frontend)"] -->|HTTPS| LB["Load Balancer"]
        LB --> W1["FastAPI\nworker 1"]
        LB --> W2["FastAPI\nworker 2"]
        LB --> W3["FastAPI\nworker N"]
        W1 & W2 & W3 --> RQ["Redis\n(job queue)"]
        RQ --> CW1["Celery worker"]
        RQ --> CW2["Celery worker"]
        W1 & W2 & W3 --> PG["PostgreSQL\n(shared DB)"]
        CW1 & CW2 --> PG
    end
```

### 9.2 Deployment Checklist

```mermaid
flowchart TD
    START([Deploy ML-ESS]) --> ENV["Set env vars\nGROQ_API_KEY, API_KEY,\nCORS_ORIGINS"]
    ENV --> DB["Initialize SQLite\n(auto on first run)"]
    DB --> SRV["Start Uvicorn\npython main.py serve"]
    SRV --> FE["Configure Frontend\nNEXT_PUBLIC_API_URL\nNEXT_PUBLIC_API_KEY"]
    FE --> BUILD["npm run build\nnpm run start"]
    BUILD --> TEST["GET /api/health\n→ status: ok"]
    TEST --> DONE([System Ready])
```

---

## 10. Conclusion

ML-ESS demonstrates how a small, well-structured multi-agent system can automate a complex, knowledge-intensive task end-to-end. By composing four focused agents — each with a clear role — the pipeline transforms a single natural language question into a cited, evaluated research report in minutes. The system is designed for clarity and correctness: low LLM temperature for deterministic outputs, retry/fallback logic for resilience, persistent job state for observability, and a clean typed API for frontend integration.

The modular agent design makes the system straightforward to extend: adding a new research phase (e.g., a fact-checking agent or a translation layer) requires only inserting a new agent function into the pipeline and extending `SharedState` with the new fields.


