"""Application configuration — loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env file (if present)")

# ── LLM Provider ─────────────────────────────────────────────────────────────
# "groq" | "huggingface" | "auto"  (auto = try Groq first, fallback to HF)
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "auto")


# #  Add logging for provider selection
# basicConfig(level=INFO, format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
# logger = getLogger(__name__)
# logger.info(f"Selected LLM provider: {LLM_PROVIDER}")

# ── Groq ─────────────────────────────────────────────────────────────────────

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY")
GROQ_API_KEY_2: str = os.getenv("GROQ_API_KEY_2", "")

GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ── HuggingFace Inference API ────────────────────────────────────────────────
HF_TOKEN: str = os.getenv("HF_TOKEN", "")
HF_MODEL: str = os.getenv("HF_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

# ── Shared LLM settings ─────────────────────────────────────────────────────
TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.3"))

# ── Search ───────────────────────────────────────────────────────────────────
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
MAX_SEARCH_QUERIES: int = int(os.getenv("MAX_SEARCH_QUERIES", "3"))
MAX_RESULTS_PER_QUERY: int = int(os.getenv("MAX_RESULTS_PER_QUERY", "5"))
MAX_CONTENT_LENGTH: int = int(os.getenv("MAX_CONTENT_LENGTH", "3000"))

# ── API ──────────────────────────────────────────────────────────────────────
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
# Static API key for all /api/research/* routes.
# Leave empty to disable auth (dev only — never in production).
API_KEY: str = os.getenv("API_KEY", "")
WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")
WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID: str = os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")

# ── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── Database ─────────────────────────────────────────────────────────────────
# Path to the SQLite database file (relative to the api/ working directory).
DB_PATH: str = os.getenv("DB_PATH", "data/jobs.db")

# ── CORS ─────────────────────────────────────────────────────────────────────
CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "https://research-agent-phi-six.vercel.app")
