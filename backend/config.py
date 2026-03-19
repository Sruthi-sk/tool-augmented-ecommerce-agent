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
MAX_TOOL_CALLS_PER_TURN = int(os.getenv("MAX_TOOL_CALLS_PER_TURN", "3"))

# Pre-indexed retrieval (Phase 0 scaffolding; not wired into runtime yet)
INDEX_DB_PATH = os.getenv("INDEX_DB_PATH", "partselect_index.db")
HELP_VECTOR_INDEX_PATH = os.getenv("HELP_VECTOR_INDEX_PATH", "help_vector_store")

# Phase 3: do not treat `seed_data.json` as truth at runtime.
# Off by default; can be enabled for local demo only.
BOOTSTRAP_FROM_SEED_ON_STARTUP = os.getenv("BOOTSTRAP_FROM_SEED_ON_STARTUP", "false").lower() in (
    "1",
    "true",
    "yes",
)
