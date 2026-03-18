"""Step 2b: Session management tests."""
import pytest
from agent.session import Session, InMemorySessionStore


def test_session_creation():
    """Session initializes with defaults."""
    s = Session(session_id="abc-123")
    assert s.session_id == "abc-123"
    assert s.appliance_type is None
    assert s.model_number is None
    assert s.part_number is None
    assert s.brand is None
    assert s.symptom is None
    assert s.last_tool_result is None
    assert s.last_source_url is None
    assert s.conversation_history == []


def test_session_update():
    """update() sets multiple fields at once."""
    s = Session(session_id="abc")
    s.update(model_number="WDT780SAEM1", appliance_type="dishwasher")
    assert s.model_number == "WDT780SAEM1"
    assert s.appliance_type == "dishwasher"


def test_session_update_rejects_unknown_fields():
    """update() ignores fields that don't exist on Session."""
    s = Session(session_id="abc")
    s.update(nonexistent_field="value")
    assert not hasattr(s, "nonexistent_field") or getattr(s, "nonexistent_field", None) is None


def test_session_clear_slot():
    """clear_slot() resets a specific field to None."""
    s = Session(session_id="abc")
    s.update(model_number="WDT780SAEM1")
    s.clear_slot("model_number")
    assert s.model_number is None


def test_session_get_context_for_llm():
    """get_context_for_llm() returns a dict with current state."""
    s = Session(session_id="abc")
    s.update(model_number="WDT780SAEM1", appliance_type="dishwasher")
    ctx = s.get_context_for_llm()
    assert isinstance(ctx, dict)
    assert ctx["model_number"] == "WDT780SAEM1"
    assert ctx["appliance_type"] == "dishwasher"


def test_session_conversation_history_windowing():
    """Conversation history is capped at the configured limit."""
    from config import CONVERSATION_HISTORY_LIMIT

    s = Session(session_id="abc")
    for i in range(CONVERSATION_HISTORY_LIMIT + 10):
        s.add_message(role="user", content=f"message {i}")
    assert len(s.conversation_history) == CONVERSATION_HISTORY_LIMIT


@pytest.mark.asyncio
async def test_in_memory_store_get_creates_new():
    """InMemorySessionStore creates a new session if none exists."""
    store = InMemorySessionStore()
    session = await store.get("new-id")
    assert session.session_id == "new-id"


@pytest.mark.asyncio
async def test_in_memory_store_save_and_get():
    """InMemorySessionStore persists sessions in memory."""
    store = InMemorySessionStore()
    session = await store.get("test-id")
    session.update(model_number="ABC123")
    await store.save(session)

    retrieved = await store.get("test-id")
    assert retrieved.model_number == "ABC123"
