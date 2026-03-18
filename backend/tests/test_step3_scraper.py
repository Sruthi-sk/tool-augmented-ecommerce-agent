"""Step 3b: PartSelect scraper tests (unit tests with mocked HTTP)."""
import pytest
from unittest.mock import AsyncMock, patch
from retrieval.scraper import PartSelectRetriever, PartData, PartSummary


SAMPLE_PART_HTML = """
<html><body>
<h1 class="title-lg">Refrigerator Water Filter</h1>
<span class="price">$24.99</span>
<div class="pd__availability">
    <span>In Stock</span>
</div>
<div class="pd__description">
    <p>This water filter fits most Whirlpool refrigerators.</p>
</div>
<div class="pd__part-number">
    <span>PartSelect Number</span> <span>PS11752778</span>
</div>
<div class="pd__mfr-number">
    <span>Manufacturer Part Number</span> <span>W10295370A</span>
</div>
</body></html>
"""

SAMPLE_SEARCH_HTML = """
<html><body>
<div class="mega-m__part">
    <a href="/PS11752778-Water-Filter.htm" class="mega-m__part__name">Water Filter</a>
    <span class="mega-m__part__price">$24.99</span>
    <span class="mega-m__part__number">PS11752778</span>
</div>
<div class="mega-m__part">
    <a href="/PS12345678-Ice-Maker.htm" class="mega-m__part__name">Ice Maker Assembly</a>
    <span class="mega-m__part__price">$89.99</span>
    <span class="mega-m__part__number">PS12345678</span>
</div>
</body></html>
"""


def test_part_data_dataclass():
    """PartData holds structured part information."""
    part = PartData(
        part_number="PS11752778",
        name="Water Filter",
        price="$24.99",
        in_stock=True,
        description="Fits most Whirlpool refrigerators",
        source_url="https://www.partselect.com/PS11752778.htm",
    )
    assert part.part_number == "PS11752778"
    assert part.in_stock is True


def test_part_summary_dataclass():
    """PartSummary holds search result information."""
    summary = PartSummary(
        part_number="PS11752778",
        name="Water Filter",
        price="$24.99",
        url="/PS11752778.htm",
    )
    assert summary.part_number == "PS11752778"


def test_retriever_instantiation():
    """PartSelectRetriever can be instantiated."""
    retriever = PartSelectRetriever()
    assert retriever is not None


@pytest.mark.asyncio
async def test_parse_part_page():
    """Retriever parses a part detail page into PartData."""
    retriever = PartSelectRetriever()
    result = retriever.parse_part_page(SAMPLE_PART_HTML, "https://www.partselect.com/PS11752778.htm")
    assert isinstance(result, PartData)
    assert result.part_number == "PS11752778"
    assert result.name == "Refrigerator Water Filter"
    assert "$24.99" in result.price


@pytest.mark.asyncio
async def test_parse_search_results():
    """Retriever parses a search results page into PartSummary list."""
    retriever = PartSelectRetriever()
    results = retriever.parse_search_results(SAMPLE_SEARCH_HTML)
    assert len(results) >= 1
    assert any(r.part_number == "PS11752778" for r in results)
