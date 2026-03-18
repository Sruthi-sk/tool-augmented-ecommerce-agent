"""Step 5c: API route tests — /api/chat endpoint."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport


def _mock_orchestrator():
    """Create a mock orchestrator that returns a valid response."""
    mock = AsyncMock()
    mock.handle_message.return_value = {"response": "Hello! How can I help?"}
    return mock


@pytest.mark.asyncio
async def test_chat_endpoint_exists():
    """POST /api/chat returns a response (not 404/405)."""
    import main
    with patch.object(main, "_orchestrator", _mock_orchestrator()):
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/chat", json={"message": "hello", "session_id": "test-1"})
    # Should not be 404 or 405
    assert resp.status_code != 404
    assert resp.status_code != 405


@pytest.mark.asyncio
async def test_chat_endpoint_requires_message():
    """POST /api/chat returns 422 without message field."""
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/chat", json={"session_id": "test-1"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_endpoint_generates_session_id():
    """POST /api/chat works without explicit session_id."""
    import main
    with patch.object(main, "_orchestrator", _mock_orchestrator()):
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code != 404
