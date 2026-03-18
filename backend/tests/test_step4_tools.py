"""Step 4: Backend tool tests. Tools are tested against seed data (no live HTTP)."""
import pytest
import json
import os
from unittest.mock import AsyncMock, patch, MagicMock

from tools.registry import ToolRegistry
from tools.search import register_search_tool
from tools.part_details import register_part_details_tool
from tools.compatibility import register_compatibility_tool
from tools.installation import register_installation_tool
from tools.symptom import register_symptom_tool


SEED_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "seed", "seed_data.json")


@pytest.fixture
def registry():
    return ToolRegistry()


@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    async def _get_or_fetch(key, fetcher, **kw):
        return await fetcher()
    cache.get_or_fetch = AsyncMock(side_effect=_get_or_fetch)
    return cache


@pytest.fixture
def mock_retriever():
    return AsyncMock()


# --- search_parts ---

@pytest.fixture
def search_registry(registry, mock_cache, mock_retriever):
    register_search_tool(registry, mock_cache, mock_retriever)
    return registry


@pytest.mark.asyncio
async def test_search_parts_returns_list(search_registry, mock_retriever):
    """search_parts returns a list of part summaries."""
    from retrieval.scraper import PartSummary
    mock_retriever.search.return_value = [
        PartSummary(part_number="PS11752778", name="Water Filter", price="$24.99", url="/PS11752778.htm"),
    ]
    result = await search_registry.execute("search_parts", {"query": "water filter", "appliance_type": "refrigerator"})
    assert isinstance(result, dict)
    assert "parts" in result
    assert len(result["parts"]) == 1
    assert result["parts"][0]["part_number"] == "PS11752778"


@pytest.mark.asyncio
async def test_search_parts_empty_results(search_registry, mock_retriever):
    """search_parts returns empty list when nothing matches."""
    mock_retriever.search.return_value = []
    result = await search_registry.execute("search_parts", {"query": "nonexistent", "appliance_type": "refrigerator"})
    assert result["parts"] == []


# --- get_part_details ---

@pytest.fixture
def details_registry(registry, mock_cache, mock_retriever):
    register_part_details_tool(registry, mock_cache, mock_retriever)
    return registry


@pytest.mark.asyncio
async def test_get_part_details_returns_data(details_registry, mock_retriever):
    """get_part_details returns structured part information."""
    from retrieval.scraper import PartData
    mock_retriever.fetch_part.return_value = PartData(
        part_number="PS11752778", name="Water Filter", price="$24.99",
        in_stock=True, description="Fits Whirlpool", source_url="https://www.partselect.com/PS11752778.htm",
    )
    result = await details_registry.execute("get_part_details", {"part_number": "PS11752778"})
    assert result["part_number"] == "PS11752778"
    assert result["name"] == "Water Filter"
    assert result["source_url"] is not None


@pytest.mark.asyncio
async def test_get_part_details_not_found(details_registry, mock_retriever):
    """get_part_details returns error when part not found."""
    mock_retriever.fetch_part.return_value = None
    result = await details_registry.execute("get_part_details", {"part_number": "PS00000000"})
    assert "error" in result


# --- check_compatibility ---

@pytest.fixture
def compat_registry(registry, mock_cache, mock_retriever):
    register_compatibility_tool(registry, mock_cache, mock_retriever)
    return registry


@pytest.mark.asyncio
async def test_check_compatibility_compatible(compat_registry, mock_retriever):
    """check_compatibility returns compatible=True when model is in list."""
    from retrieval.scraper import PartData
    mock_retriever.fetch_part.return_value = PartData(
        part_number="PS11752778", name="Water Filter", price="$24.99",
        in_stock=True, description="Fits Whirlpool", source_url="https://www.partselect.com/PS11752778.htm",
        compatible_models=["WDT780SAEM1", "WRF535SWHZ"],
    )
    result = await compat_registry.execute("check_compatibility", {
        "part_number": "PS11752778", "model_number": "WDT780SAEM1",
    })
    assert result["compatible"] is True


@pytest.mark.asyncio
async def test_check_compatibility_incompatible(compat_registry, mock_retriever):
    """check_compatibility returns compatible=False when model not in list."""
    from retrieval.scraper import PartData
    mock_retriever.fetch_part.return_value = PartData(
        part_number="PS11752778", name="Water Filter", price="$24.99",
        in_stock=True, description="Fits Whirlpool", source_url="https://www.partselect.com/PS11752778.htm",
        compatible_models=["WDT780SAEM1"],
    )
    result = await compat_registry.execute("check_compatibility", {
        "part_number": "PS11752778", "model_number": "UNKNOWN123",
    })
    assert result["compatible"] is False


# --- get_installation_guide ---

@pytest.fixture
def install_registry(registry, mock_cache, mock_retriever):
    register_installation_tool(registry, mock_cache, mock_retriever)
    return registry


@pytest.mark.asyncio
async def test_get_installation_guide(install_registry, mock_retriever):
    """get_installation_guide returns steps."""
    from retrieval.scraper import PartData
    mock_retriever.fetch_part.return_value = PartData(
        part_number="PS11752778", name="Water Filter", price="$24.99",
        in_stock=True, description="Fits Whirlpool", source_url="https://www.partselect.com/PS11752778.htm",
        installation_steps=["Turn off water supply", "Remove old filter", "Insert new filter"],
    )
    result = await install_registry.execute("get_installation_guide", {"part_number": "PS11752778"})
    assert "steps" in result
    assert len(result["steps"]) >= 1
    assert result["source_url"] is not None


@pytest.mark.asyncio
async def test_get_installation_guide_not_found(install_registry, mock_retriever):
    """get_installation_guide returns error when part not found."""
    mock_retriever.fetch_part.return_value = None
    result = await install_registry.execute("get_installation_guide", {"part_number": "PS00000000"})
    assert "error" in result


# --- diagnose_symptom ---

@pytest.fixture
def symptom_registry(registry, mock_cache, mock_retriever):
    register_symptom_tool(registry, mock_cache, mock_retriever)
    return registry


@pytest.mark.asyncio
async def test_diagnose_symptom_returns_causes(symptom_registry):
    """diagnose_symptom returns possible causes and parts."""
    result = await symptom_registry.execute("diagnose_symptom", {
        "appliance_type": "refrigerator",
        "symptom": "ice maker not working",
    })
    assert "causes" in result
    assert isinstance(result["causes"], list)
    assert len(result["causes"]) >= 1


@pytest.mark.asyncio
async def test_diagnose_symptom_with_model(symptom_registry):
    """diagnose_symptom accepts optional model_number."""
    result = await symptom_registry.execute("diagnose_symptom", {
        "appliance_type": "refrigerator",
        "symptom": "leaking water",
        "model_number": "WRF535SWHZ",
    })
    assert "causes" in result


# --- All tools register on shared registry ---

def test_all_tools_register(mock_cache, mock_retriever):
    """All 5 tools can register on a single registry."""
    reg = ToolRegistry()
    register_search_tool(reg, mock_cache, mock_retriever)
    register_part_details_tool(reg, mock_cache, mock_retriever)
    register_compatibility_tool(reg, mock_cache, mock_retriever)
    register_installation_tool(reg, mock_cache, mock_retriever)
    register_symptom_tool(reg, mock_cache, mock_retriever)

    tools = reg.list_tools()
    names = {t["name"] for t in tools}
    assert names == {"search_parts", "get_part_details", "check_compatibility", "get_installation_guide", "diagnose_symptom"}


def test_all_tools_generate_openai_schemas(mock_cache, mock_retriever):
    """All tools produce valid OpenAI function schemas."""
    reg = ToolRegistry()
    register_search_tool(reg, mock_cache, mock_retriever)
    register_part_details_tool(reg, mock_cache, mock_retriever)
    register_compatibility_tool(reg, mock_cache, mock_retriever)
    register_installation_tool(reg, mock_cache, mock_retriever)
    register_symptom_tool(reg, mock_cache, mock_retriever)

    schemas = reg.get_schemas("openai")
    assert len(schemas) == 5
    for s in schemas:
        assert s["type"] == "function"
        assert "name" in s["function"]
        assert "parameters" in s["function"]
