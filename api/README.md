# API — Multi-Agent Research Assistant

FastAPI backend that orchestrates the four-agent research pipeline.

## Structure

```
api/
├── app/
│   ├── agents/
│   │   ├── search.py       # Query generation, web scraping, evidence extraction
│   │   ├── synthesis.py    # Theme identification, contradiction detection
│   │   ├── report.py       # Structured report generation
│   │   └── evaluator.py    # Quality scoring (coverage, faithfulness, …)
│   ├── api/
│   │   ├── app.py          # FastAPI application factory
│   │   ├── routes.py       # All REST endpoints
│   │   ├── auth.py         # X-API-Key header authentication
│   │   └── webhook.py      # WhatsApp Business webhook
│   ├── core/
│   │   ├── config.py       # Environment variable loading
│   │   ├── pipeline.py     # Agent orchestration
│   │   ├── llm.py          # Groq / HuggingFace provider abstraction
│   │   ├── jobs.py         # Background job queue
│   │   └── store.py        # SQLite persistence
│   └── models/
│       ├── api.py          # Request / response schemas
│       └── state.py        # Pipeline state models
├── tests/
├── main.py                 # CLI & server entry point
├── pyproject.toml
└── requirements.txt
```

## Setup

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example .env       # fill in your API keys
```

For development dependencies (pytest, etc.):

```bash
pip install -e ".[dev]"
```

## Running

**API server:**
```bash
python main.py serve
python main.py serve --port 8080 --reload   # dev mode with auto-reload
```

Server starts at `http://localhost:8000`. Interactive docs at `/docs`.

**CLI (no server):**
```bash
# Single question
python main.py research "What are the trade-offs between CNNs and Vision Transformers?"

# Run built-in example prompts
python main.py research
```

## Environment variables

Place in `api/.env` (copy from `../.env.example`).

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `auto` | `groq`, `huggingface`, or `auto` (tries Groq first) |
| `GROQ_API_KEY` | — | Groq API key |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model ID |
| `GROQ_API_KEY_2` | — | Optional fallback Groq key |
| `HF_TOKEN` | — | HuggingFace API token |
| `HF_MODEL` | `meta-llama/Llama-3.3-70B-Instruct` | HuggingFace model ID |
| `TEMPERATURE` | `0.3` | LLM sampling temperature |
| `TAVILY_API_KEY` | — | Tavily search key (falls back to DuckDuckGo if unset) |
| `MAX_SEARCH_QUERIES` | `3` | Queries generated per job |
| `MAX_RESULTS_PER_QUERY` | `5` | Web results fetched per query |
| `MAX_CONTENT_LENGTH` | `3000` | Max characters scraped per page |
| `API_KEY` | — | Static key for `X-API-Key` auth (leave empty to disable) |
| `API_HOST` | `0.0.0.0` | Bind address |
| `API_PORT` | `8000` | Bind port |
| `DB_PATH` | `data/jobs.db` | SQLite file path (relative to `api/`) |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |

Generate a strong `API_KEY`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Endpoints

All `/api/research/*` endpoints require `X-API-Key: <key>` when `API_KEY` is set.

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/research` | Submit a question — returns `job_id` (HTTP 202) |
| `GET` | `/api/research` | List all jobs |
| `GET` | `/api/research/{id}` | Job status, report, and evaluation scores |
| `GET` | `/api/research/{id}/reasoning` | Full reasoning trace (queries, sources, themes, …) |
| `GET` | `/api/research/{id}/events` | SSE stream of live pipeline events |
| `GET` | `/api/research/{id}/pdf` | Download report as PDF |
| `DELETE` | `/api/research/{id}` | Delete a job |
| `DELETE` | `/api/research` | Delete all jobs |
| `GET` | `/api/health` | Health check (no auth) |

**Submit a job:**
```bash
curl -X POST http://localhost:8000/api/research \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"question": "What are the risks of AI in healthcare?"}'
# → {"job_id": "...", "status": "pending", "question": "..."}
```

**Poll until complete:**
```bash
curl http://localhost:8000/api/research/<job_id> \
  -H "X-API-Key: your-key"
```

**Stream events (SSE):**
```bash
curl -N http://localhost:8000/api/research/<job_id>/events \
  -H "X-API-Key: your-key"
```

## Job lifecycle

```
pending → searching → synthesising → reporting → evaluating → completed
                                                             ↘ failed
```

## Tests

```bash
pytest tests/
```

## Deployment

### Docker

There is no `Dockerfile` yet — here is a minimal one to place at `api/Dockerfile`:

```dockerfile
FROM python:3.11-slim

# WeasyPrint system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0 \
    libffi-dev shared-mime-info fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["python", "main.py", "serve"]
```

Build and run:

```bash
docker build -t research-api .
docker run -d \
  --name research-api \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  research-api
```

The `-v` mount keeps the SQLite database outside the container so it survives restarts.

### Production settings

Set these in your `.env` or deployment environment:

```env
API_KEY=<strong-random-key>          # never leave empty in production
CORS_ORIGINS=https://yourdomain.com  # restrict to your frontend origin
API_HOST=0.0.0.0
API_PORT=8000
DB_PATH=data/jobs.db
```

Run with multiple workers if you expect concurrent jobs (each job uses a background thread, so a single worker is usually fine):

```bash
python main.py serve --host 0.0.0.0 --port 8000
# or directly via uvicorn for more control:
uvicorn app.api.app:app --host 0.0.0.0 --port 8000 --workers 2
```

### systemd (Linux)

Create `/etc/systemd/system/research-api.service`:

```ini
[Unit]
Description=Multi-Agent Research Assistant API
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/research-api/api
EnvironmentFile=/opt/research-api/api/.env
ExecStart=/opt/research-api/api/venv/bin/python main.py serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now research-api
sudo journalctl -u research-api -f   # view logs
```

### Reverse proxy (nginx)

```nginx
location /api/ {
    proxy_pass         http://127.0.0.1:8000;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;

    # Required for SSE (/events endpoint)
    proxy_buffering    off;
    proxy_cache        off;
    proxy_read_timeout 3600s;
}
```
