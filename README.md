📁 Project Structure
text
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
🧰 Technology Stack
Layer	Technology
Backend	Python 3.11+, FastAPI, Uvicorn
LLM (Primary)	Groq API — llama-3.3-70b-versatile
LLM (Fallback)	HuggingFace Inference — Llama-3.3-70B-Instruct
Web Search	DuckDuckGo (default) + Tavily (optional)
Web Scraping	httpx + BeautifulSoup4
Validation	Pydantic v2
Database	SQLite (WAL mode)
PDF Export	WeasyPrint
Frontend	Next.js 16, React 19, TypeScript, Tailwind CSS v4
Hosting (Backend)	Render — Python/FastAPI service
🚀 Getting Started
1. Clone the Repository
bash
git clone https://github.com/samson19977/AI_agentic_reasoning.git
cd AI_agentic_reasoning
2. Backend Setup
bash
cd api
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env           # Edit .env with your API keys
3. Frontend Setup
bash
cd frontend
npm install
Create frontend/.env.local:

env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_API_KEY=your-api-key   # Must match API_KEY in api/.env
🏃 Running the Application
Start the API Server (port 8000)
bash
cd api
source venv/bin/activate
python main.py serve

# Development mode with auto-reload:
python main.py serve --reload
Start the Frontend (port 3000)
bash
cd frontend
npm run dev
Run in CLI Mode (single question, no server)
bash
cd api
python main.py research "What are the trade-offs between CNNs and Vision Transformers?"
🔐 Environment Variables
Copy .env.example to api/.env and configure:

Variable	Default	Description
LLM_PROVIDER	auto	groq, huggingface, or auto (Groq first)
GROQ_API_KEY	—	Primary Groq API key
GROQ_API_KEY_2	—	Secondary Groq key (rate-limit headroom)
GROQ_MODEL	llama-3.3-70b-versatile	Groq model ID
HF_TOKEN	—	HuggingFace API token
HF_MODEL	meta-llama/Llama-3.3-70B-Instruct	HuggingFace model ID
TEMPERATURE	0.3	LLM sampling temperature
TAVILY_API_KEY	—	Tavily search key (falls back to DuckDuckGo)
MAX_SEARCH_QUERIES	3	Search queries generated per job
MAX_RESULTS_PER_QUERY	5	Web results fetched per query
MAX_CONTENT_LENGTH	3000	Max characters scraped per page
API_KEY	—	Static key for X-API-Key auth
API_HOST	0.0.0.0	Bind address
API_PORT	8000	Bind port
DB_PATH	data/jobs.db	SQLite file path
CORS_ORIGINS	http://localhost:3000	Comma-separated allowed origins
Generate a secure API_KEY:

bash
python -c "import secrets; print(secrets.token_hex(32))"
