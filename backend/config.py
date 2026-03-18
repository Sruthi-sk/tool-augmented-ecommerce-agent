import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # "openai" or "anthropic"

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", "24"))
CACHE_DB_PATH = os.getenv("CACHE_DB_PATH", "cache.db")

CONVERSATION_HISTORY_LIMIT = 20
