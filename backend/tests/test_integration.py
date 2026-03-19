"""Integration tests — real LLM + live PartSelect retrieval.

Run with:  pytest -m integration tests/test_integration.py -v --tb=short
Requires:  OPENAI_API_KEY or ANTHROPIC_API_KEY in env / .env
"""
import logging
import os

import pytest

from config import LLM_PROVIDER, OPENAI_API_KEY, ANTHROPIC_API_KEY

logger = logging.getLogger("integration")
logger.setLevel(logging.DEBUG)

pytestmark = pytest.mark.integration

# ── Guards ──────────────────────────────────────────────────────────────────

_has_api_key = bool(OPENAI_API_KEY or ANTHROPIC_API_KEY)
if not _has_api_key:
    pytestmark = [pytestmark, pytest.mark.skip("No API key set")]


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
async def orchestrator(tmp_path_factory):
    """Build a real orchestrator with live provider and pre-indexed retrieval."""
    from agent.orchestrator import AgentOrchestrator
    from agent.session import InMemorySessionStore
    from index.structured_store import StructuredStore
    from index.help_vector_store import HelpVectorIndex
    from index.knowledge_service import KnowledgeService
    from tools.registry import ToolRegistry
    from tools.search import register_search_tool
    from tools.part_details import register_part_details_tool
    from tools.compatibility import register_compatibility_tool
    from tools.installation import register_installation_tool
    from tools.symptom import register_symptom_tool

    from ingestion.build_partselect_index import ensure_structured_index

    db_path = str(tmp_path_factory.mktemp("index") / "test_partselect_index.db")
    await ensure_structured_index(db_path=db_path, bootstrap_from_seed=True)

    structured_store = StructuredStore(db_path=db_path)
    await structured_store.initialize()
    help_vector_index = HelpVectorIndex(structured_db_path=db_path)
    await help_vector_index.initialize()
    knowledge_service = KnowledgeService(
        structured_store=structured_store, help_vector_index=help_vector_index
    )
    session_store = InMemorySessionStore()

    registry = ToolRegistry()
    register_search_tool(registry, knowledge_service=knowledge_service)
    register_part_details_tool(registry, knowledge_service=knowledge_service)
    register_compatibility_tool(registry, knowledge_service=knowledge_service)
    register_installation_tool(registry, knowledge_service=knowledge_service)
    register_symptom_tool(registry, knowledge_service=knowledge_service)

    provider_name = LLM_PROVIDER
    if provider_name == "anthropic":
        from providers.claude_provider import ClaudeProvider
        provider = ClaudeProvider()
    else:
        from providers.openai_provider import OpenAIProvider
        provider = OpenAIProvider()

    orch = AgentOrchestrator(
        provider=provider,
        registry=registry,
        session_store=session_store,
        provider_name=provider_name,
    )

    yield orch

    await structured_store.close()
    await help_vector_index.close()


# ── Helpers ─────────────────────────────────────────────────────────────────

def _log_result(label: str, result: dict):
    """Log the full result for demo prep / debugging."""
    logger.info(
        "\n=== %s ===\ntype=%s  response_type=%s\nmessage=%s\nsource_url=%s\nsuggested_actions=%s\ndetail_data keys=%s\n",
        label,
        result.get("type"),
        result.get("response_type"),
        result.get("message", "")[:300],
        result.get("source_url"),
        result.get("suggested_actions"),
        list(result["detail_data"].keys()) if result.get("detail_data") else None,
    )


def _assert_valid_response(result: dict):
    """Common structure checks for any successful orchestrator result."""
    assert result["type"] in ("response", "refusal", "error")
    assert isinstance(result["message"], str)
    assert len(result["message"]) > 0


# ── Tests ───────────────────────────────────────────────────────────────────

class TestPartLookup:
    """Part search and detail retrieval against live PartSelect."""

    async def test_search_parts(self, orchestrator):
        result = await orchestrator.handle_message(
            "Find me refrigerator water filters", "integ-search-1"
        )
        _log_result("search_parts", result)
        _assert_valid_response(result)
        assert result["type"] == "response"

    async def test_part_details(self, orchestrator):
        result = await orchestrator.handle_message(
            "Show me details for part PS11752778", "integ-detail-1"
        )
        _log_result("part_details", result)
        _assert_valid_response(result)
        assert result["type"] == "response"
        # The LLM should have called get_part_details and returned real data
        if result.get("detail_data"):
            assert "part_number" in result["detail_data"] or "error" in result["detail_data"]


class TestCompatibility:
    """Compatibility checks with real parts and models."""

    async def test_compatible_pair(self, orchestrator):
        result = await orchestrator.handle_message(
            "Is part PS11752778 compatible with model WRS325SDHZ?",
            "integ-compat-1",
        )
        _log_result("compatibility_check", result)
        _assert_valid_response(result)
        assert result["type"] == "response"

    async def test_incompatible_or_unknown_model(self, orchestrator):
        result = await orchestrator.handle_message(
            "Is part PS11752778 compatible with model FAKEMODEL999?",
            "integ-compat-2",
        )
        _log_result("compatibility_unknown", result)
        _assert_valid_response(result)
        # Should still respond gracefully — not crash
        assert result["type"] == "response"


class TestSymptomTroubleshooting:
    """Symptom diagnosis with the built-in knowledge base."""

    async def test_refrigerator_symptom(self, orchestrator):
        result = await orchestrator.handle_message(
            "My Whirlpool refrigerator is not making ice", "integ-symptom-1"
        )
        _log_result("symptom_refrigerator", result)
        _assert_valid_response(result)
        assert result["type"] == "response"

    async def test_dishwasher_symptom(self, orchestrator):
        result = await orchestrator.handle_message(
            "My dishwasher won't drain", "integ-symptom-2"
        )
        _log_result("symptom_dishwasher", result)
        _assert_valid_response(result)
        assert result["type"] == "response"


class TestErrorHandling:
    """Graceful degradation under adverse conditions."""

    async def test_nonexistent_part(self, orchestrator):
        """Retriever returns nothing — LLM should say so honestly."""
        result = await orchestrator.handle_message(
            "Show me details for part PS00000001", "integ-err-1"
        )
        _log_result("nonexistent_part", result)
        _assert_valid_response(result)
        # Should not crash; either an honest "not found" response or error
        assert result["type"] in ("response", "error")

    async def test_out_of_scope_rejected(self, orchestrator):
        """Off-topic message should be refused without calling the LLM."""
        result = await orchestrator.handle_message(
            "What is the weather in New York?", "integ-err-2"
        )
        _log_result("out_of_scope", result)
        assert result["type"] == "refusal"

    async def test_vague_query_handled(self, orchestrator):
        """Ambiguous but in-scope message should not crash."""
        result = await orchestrator.handle_message(
            "I need a part", "integ-err-3"
        )
        _log_result("vague_query", result)
        _assert_valid_response(result)
        assert result["type"] in ("response", "error")


class TestConversationFlow:
    """Multi-turn conversation with session state."""

    async def test_followup_uses_context(self, orchestrator):
        sid = "integ-convo-1"
        # First message establishes context
        r1 = await orchestrator.handle_message(
            "Show me details for part PS11752778", sid
        )
        _log_result("convo_turn_1", r1)
        _assert_valid_response(r1)

        # Follow-up should use session context (part number already known)
        r2 = await orchestrator.handle_message(
            "Is it compatible with WRS325SDHZ?", sid
        )
        _log_result("convo_turn_2", r2)
        _assert_valid_response(r2)
        assert r2["type"] == "response"
