"""Tests for symptom-first diagnosis flow (repair_guide_text field)."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from index.knowledge_service import KnowledgeService


def _make_service(structured_causes=None, help_hits=None):
    """Build a KnowledgeService with mocked sub-stores."""
    structured_store = AsyncMock()
    help_index = AsyncMock()

    structured_store.get_troubleshooting_causes = AsyncMock(
        return_value=structured_causes or {
            "likely_causes": [],
            "recommended_parts": [],
            "source_urls": [],
            "matched_symptom": "dishwasher-not-draining",
        }
    )
    help_index.search_help = AsyncMock(return_value=help_hits or [])

    return KnowledgeService(
        structured_store=structured_store,
        help_vector_index=help_index,
    )


# --- repair_guide_text presence in diagnose_troubleshooting ---

@pytest.mark.asyncio
async def test_repair_guide_text_present_when_help_hits_exist():
    """repair_guide_text is a non-empty string when search_help returns at least one hit."""
    service = _make_service(
        help_hits=[{
            "chunk_text": "Dishwasher not draining: check drain hose, pump, check valve.",
            "source_url": "https://ps.com/repair/dishwasher/not-draining/",
            "symptom_key": "dishwasher-not-draining",
            "score": 0.9,
        }]
    )
    result = await service.diagnose_troubleshooting("dishwasher", "not draining")
    assert "repair_guide_text" in result
    assert isinstance(result["repair_guide_text"], str)
    assert len(result["repair_guide_text"]) > 0


@pytest.mark.asyncio
async def test_repair_guide_text_none_when_no_help_hits():
    """repair_guide_text is None when search_help returns an empty list."""
    service = _make_service(help_hits=[])
    result = await service.diagnose_troubleshooting("dishwasher", "not draining")
    assert "repair_guide_text" in result
    assert result["repair_guide_text"] is None


@pytest.mark.asyncio
async def test_likely_causes_populated_when_repair_guide_text_none():
    """likely_causes is non-empty even when repair_guide_text is None (structured data path)."""
    service = _make_service(
        structured_causes={
            "likely_causes": [{"cause": "Clogged drain hose", "part_type": "Drain Hose", "likelihood": "high"}],
            "recommended_parts": [],
            "source_urls": ["https://ps.com/repair/dishwasher/not-draining/"],
            "matched_symptom": "dishwasher-not-draining",
        },
        help_hits=[],  # no guide text
    )
    result = await service.diagnose_troubleshooting("dishwasher", "not draining")
    assert result["repair_guide_text"] is None
    assert len(result.get("likely_causes") or []) > 0


@pytest.mark.asyncio
async def test_repair_guide_text_present_on_structured_hit_path():
    """repair_guide_text is included even when structured causes are found."""
    service = _make_service(
        structured_causes={
            "likely_causes": [{"cause": "Clogged drain hose", "part_type": "Drain Hose", "likelihood": "high"}],
            "recommended_parts": [],
            "source_urls": [],
            "matched_symptom": "dishwasher-not-draining",
        },
        help_hits=[{
            "chunk_text": "Guide: inspect drain hose first.",
            "source_url": "https://ps.com/",
            "symptom_key": "dishwasher-not-draining",
            "score": 0.95,
        }],
    )
    result = await service.diagnose_troubleshooting("dishwasher", "not draining")
    assert result.get("repair_guide_text") == "Guide: inspect drain hose first."


# --- repair_guide_text propagation through the tool layer ---

@pytest.mark.asyncio
async def test_diagnose_symptom_tool_passes_repair_guide_text_through():
    """repair_guide_text from knowledge_service survives the diagnose_symptom return dict."""
    from tools.registry import ToolRegistry
    from tools.symptom import register_symptom_tool

    mock_ks = AsyncMock()
    mock_ks.diagnose_troubleshooting = AsyncMock(return_value={
        "causes": [{"cause": "Clogged drain hose", "part_type": "Drain Hose", "likelihood": "high"}],
        "likely_causes": [{"cause": "Clogged drain hose", "part_type": "Drain Hose", "likelihood": "high"}],
        "recommended_parts": [],
        "source_urls": ["https://ps.com/repair/dishwasher/not-draining/"],
        "matched_symptom": "dishwasher-not-draining",
        "repair_guide_text": "Check the drain hose for kinks. Inspect the pump.",
    })

    reg = ToolRegistry()
    register_symptom_tool(reg, mock_ks)

    result = await reg.execute("diagnose_symptom", {"appliance_type": "dishwasher", "symptom": "not draining"})
    assert "repair_guide_text" in result
    assert result["repair_guide_text"] == "Check the drain hose for kinks. Inspect the pump."


# --- suggested_actions branch ---

def test_suggest_actions_triage_chips_when_repair_guide_text_present():
    """_suggest_actions returns triage chips when detail_data has repair_guide_text."""
    from agent.orchestrator import AgentOrchestrator
    orch = AgentOrchestrator(
        provider=AsyncMock(),
        registry=MagicMock(),
        session_store=AsyncMock(),
    )
    detail = {"repair_guide_text": "some guide text", "causes": []}
    actions = orch._suggest_actions("troubleshooting", detail)
    assert "Find replacement parts" not in actions
    assert len(actions) > 0


def test_suggest_actions_part_chips_when_no_repair_guide_text():
    """_suggest_actions returns part-finding chips when repair_guide_text is absent."""
    from agent.orchestrator import AgentOrchestrator
    orch = AgentOrchestrator(
        provider=AsyncMock(),
        registry=MagicMock(),
        session_store=AsyncMock(),
    )
    detail = {"causes": []}  # no repair_guide_text key
    actions = orch._suggest_actions("troubleshooting", detail)
    assert "Find replacement parts" in actions
