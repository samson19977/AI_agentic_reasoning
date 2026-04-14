# ML-ESS: Multi-Agent Research Assistant

An AI-powered system that searches, synthesizes, and reports on research questions using four sequential agents.

## How It Works

Question → Search → Synthesis → Report → Evaluator → Scored Report

| Agent | Task |
|-------|------|
| Search | Fetches web sources and extracts evidence |
| Synthesis | Groups evidence into themes |
| Report | Writes a cited Markdown report |
| Evaluator | Scores quality and checks for hallucinations |

Jobs run in the background with SQLite persistence. The frontend shows live progress via SSE.

## Tech Stack

Backend: Python, FastAPI, Uvicorn
LLM: Groq (Llama 3.3 70B) / HuggingFace fallback
Search: DuckDuckGo / Tavily
Database: SQLite
Frontend: Next.js, TypeScript, Tailwind
Hosting: Render (BE), Vercel (FE)

## Project Structure

ml-ess/
├── api/                # FastAPI backend
│   ├── app/agents/     # Search, Synthesis, Report, Evaluator
│   ├── app/core/       # Pipeline, LLM, Jobs, Store
│   └── app/api/        # Routes, Auth, Webhooks
└── frontend/           # Next.js UI

## Getting Started

Clone the repo:
git clone https://github.com/samson19977/AI_agentic_reasoning.git
cd AI_agentic_reasoning

Backend setup:
cd api
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Groq API key

Frontend setup:
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
echo "NEXT_PUBLIC_API_KEY=your-api-key" >> .env.local

## Running

Start backend (port 8000):
cd api
source venv/bin/activate
python main.py serve

Start frontend (port 3000):
cd frontend
npm run dev

CLI mode (no server):
cd api
python main.py research "Your research question"

## API Endpoints

POST   /api/research          - Submit a question
GET    /api/research          - List all jobs
GET    /api/research/{id}     - Get job status and report
GET    /api/research/{id}/events - SSE live progress
DELETE /api/research/{id}     - Delete a job

## Environment Variables

Create api/.env with:
GROQ_API_KEY=your_groq_key
API_KEY=your_secret_key
TEMPERATURE=0.3
MAX_SEARCH_QUERIES=3

Generate a secure API key:
python -c "import secrets; print(secrets.token_hex(32))"

## Telegram Bot

Set these in api/.env:
TELEGRAM_BOT_TOKEN=your_bot_token
WEBHOOK_SECRET=your_secret

Register webhook:
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://your-domain.com/api/webhook/telegram"

## Deployment

Backend: Deploy to Render with api/.env variables
Frontend: Deploy to Vercel with NEXT_PUBLIC_API_URL and NEXT_PUBLIC_API_KEY

## Tests

cd api
pytest tests/

## Extending

To add a new agent:
1. Create agent function in api/app/agents/
2. Add fields to SharedState in api/app/models/state.py
3. Add agent call in api/app/core/pipeline.py

## Acknowledgements

Built during the AIMS Research Innovation Centre Doctoral Training School 2026.
Thanks to Prof. Wilfred Ndifon and the AIMS RIC team.

## Author

Samson Niyizurugero
