import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import FRONTEND_URL, LLM_PROVIDER, CACHE_DB_PATH
from agent.orchestrator import AgentOrchestrator
from agent.session import InMemorySessionStore
from retrieval.cache import CacheLayer
from retrieval.scraper import PartSelectRetriever
from tools.registry import ToolRegistry
from tools.search import register_search_tool
from tools.part_details import register_part_details_tool
from tools.compatibility import register_compatibility_tool
from tools.installation import register_installation_tool
from tools.symptom import register_symptom_tool

# Global orchestrator — initialized on startup
_orchestrator: Optional[AgentOrchestrator] = None


def _create_provider(provider_name: str):
    """Create the configured LLM provider."""
    if provider_name == "anthropic":
        from providers.claude_provider import ClaudeProvider
        return ClaudeProvider()
    else:
        from providers.openai_provider import OpenAIProvider
        return OpenAIProvider()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator

    # Initialize components
    cache = CacheLayer(CACHE_DB_PATH)
    await cache.initialize()

    retriever = PartSelectRetriever()
    session_store = InMemorySessionStore()

    # Register all tools
    registry = ToolRegistry()
    register_search_tool(registry, cache, retriever)
    register_part_details_tool(registry, cache, retriever)
    register_compatibility_tool(registry, cache, retriever)
    register_installation_tool(registry, cache, retriever)
    register_symptom_tool(registry, cache, retriever)

    # Create provider and orchestrator
    provider = _create_provider(LLM_PROVIDER)
    _orchestrator = AgentOrchestrator(
        provider=provider,
        registry=registry,
        session_store=session_store,
        provider_name=LLM_PROVIDER,
    )

    yield

    # Cleanup
    await cache.close()
    await retriever.close()


app = FastAPI(title="PartSelect Chat Agent", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    result = await _orchestrator.handle_message(request.message, session_id)
    result["session_id"] = session_id
    return result
