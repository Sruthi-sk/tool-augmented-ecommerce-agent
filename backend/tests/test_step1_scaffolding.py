"""Step 1: Verify project scaffolding is correctly set up."""
import pytest
from httpx import AsyncClient, ASGITransport

from main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """FastAPI app serves /health."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_cors_allows_frontend():
    """CORS is configured for the frontend origin."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert resp.status_code == 200
    assert "http://localhost:3000" in resp.headers.get("access-control-allow-origin", "")


def test_config_defaults():
    """Config loads with sensible defaults."""
    from config import LLM_PROVIDER, CACHE_TTL_HOURS, CONVERSATION_HISTORY_LIMIT

    assert LLM_PROVIDER in ("openai", "anthropic")
    assert CACHE_TTL_HOURS > 0
    assert CONVERSATION_HISTORY_LIMIT == 20
