"""
Tests for backend/ingestion/crawl_partselect.py

Two layers:
  - Unit tests (no network): fixture HTML → parser → assert fields
  - Live tests (network + Playwright): Crawl4AI fetches real PartSelect pages

Run unit tests only (default):
    pytest tests/test_ingestion_crawl.py

Run live tests (requires Playwright and internet):
    pytest tests/test_ingestion_crawl.py -m live
"""

import re
import pytest
import aiosqlite

from ingestion.crawl_partselect import _parse_part_detail, _discover_part_urls, _write_part


# ─── fixture HTML ─────────────────────────────────────────────────────────────
# Mirrors the actual PartSelect page structure based on confirmed selectors.

PART_DETAIL_HTML = """
<html><body>
<h1 class="title-lg">Refrigerator Water Filter</h1>

<span itemprop="productID">PS11752778</span>
<span itemprop="mpn">W10295370A</span>

<span class="js-partPrice">$24.99</span>

<div class="pd__availability">
    <span class="js-inventory-message">In Stock</span>
</div>

<div class="pd__description">
    Genuine OEM replacement water filter for Whirlpool refrigerators.
    Reduces chlorine taste and odor.
</div>

<!-- Symptoms via repair story titles (actual PartSelect structure) -->
<div class="repair-story"><h2 class="repair-story__title mb-3 mb-lg-4 js-searchKeys">Water dispenser not working</h2></div>
<div class="repair-story"><h2 class="repair-story__title mb-3 mb-lg-4 js-searchKeys">Ice maker not making ice</h2></div>
<div class="repair-story"><h2 class="repair-story__title mb-3 mb-lg-4 js-searchKeys">Water has bad taste or odor</h2></div>

<!-- Compatible models -->
<div id="compatible-models">
    <div class="pd__crossref__part"><a href="#">WRS325FDAM04</a></div>
    <div class="pd__crossref__part"><a href="#">WRF535SWHZ00</a></div>
    <div class="pd__crossref__part"><a href="#">WRS571CIHZ00</a></div>
</div>

<!-- Installation via repair story instructions (actual PartSelect structure) -->
<div class="repair-story">
    <div class="repair-story__instruction">Turn off the ice maker. Locate the filter housing in the upper right corner of the fresh food section. Turn the old filter counterclockwise to remove it. Insert the new filter and turn clockwise until it locks. Run two gallons of water to flush.</div>
</div>
<div class="repair-story">
    <div class="repair-story__instruction">I watched a YouTube video before starting. The job took about 15 minutes. Twist out old filter and push in new one until it clicks.</div>
</div>
</body></html>
"""

# Category page: contains links to part detail pages
CATEGORY_HTML = """
<html><body>
<h1>Refrigerator Parts</h1>
<ul>
  <li><a href="/PS11752778-Whirlpool-W10295370A-Refrigerator-Water-Filter.htm">Water Filter</a></li>
  <li><a href="/PS11746337-Whirlpool-WPW10321304-Ice-Maker-Assembly.htm">Ice Maker Assembly</a></li>
  <li><a href="/PS11703224-GE-WR55X26671-Main-Control-Board.htm">Main Control Board</a></li>
  <li><a href="/about">About Us</a></li>
  <li><a href="/contact">Contact</a></li>
</ul>
</body></html>
"""

# Part page with no PS number — used to test graceful parse failure
INVALID_PART_HTML = """
<html><body>
<h1>404 - Part not found</h1>
</body></html>
"""


# ─── unit: _parse_part_detail ─────────────────────────────────────────────────


def test_parse_extracts_part_number():
    part = _parse_part_detail(PART_DETAIL_HTML, "https://www.partselect.com/PS11752778.htm", "refrigerator")
    assert part is not None
    assert part["part_number"] == "PS11752778"


def test_parse_extracts_name():
    part = _parse_part_detail(PART_DETAIL_HTML, "https://www.partselect.com/PS11752778.htm", "refrigerator")
    assert part["name"] == "Refrigerator Water Filter"


def test_parse_extracts_price():
    part = _parse_part_detail(PART_DETAIL_HTML, "https://www.partselect.com/PS11752778.htm", "refrigerator")
    assert "$24.99" in part["price"]


def test_parse_detects_in_stock():
    part = _parse_part_detail(PART_DETAIL_HTML, "https://www.partselect.com/PS11752778.htm", "refrigerator")
    assert part["in_stock"] is True


def test_parse_extracts_description():
    part = _parse_part_detail(PART_DETAIL_HTML, "https://www.partselect.com/PS11752778.htm", "refrigerator")
    assert "water filter" in part["description"].lower()


def test_parse_extracts_mpn():
    part = _parse_part_detail(PART_DETAIL_HTML, "https://www.partselect.com/PS11752778.htm", "refrigerator")
    assert part["manufacturer_part_number"] == "W10295370A"


def test_parse_extracts_symptoms():
    part = _parse_part_detail(PART_DETAIL_HTML, "https://www.partselect.com/PS11752778.htm", "refrigerator")
    assert len(part["symptoms"]) == 3
    # normalized keys are lowercase with underscores
    joined = " ".join(part["symptoms"])
    assert "water" in joined


def test_parse_extracts_compatible_models():
    part = _parse_part_detail(PART_DETAIL_HTML, "https://www.partselect.com/PS11752778.htm", "refrigerator")
    assert "WRS325FDAM04" in part["compatible_models"]
    assert "WRF535SWHZ00" in part["compatible_models"]
    assert len(part["compatible_models"]) == 3


def test_parse_extracts_installation_steps():
    part = _parse_part_detail(PART_DETAIL_HTML, "https://www.partselect.com/PS11752778.htm", "refrigerator")
    assert len(part["installation_steps"]) == 2
    assert "ice maker" in part["installation_steps"][0].lower()


def test_parse_sets_appliance_type():
    part = _parse_part_detail(PART_DETAIL_HTML, "https://www.partselect.com/PS11752778.htm", "refrigerator")
    assert part["appliance_type"] == "refrigerator"


def test_parse_falls_back_to_url_for_part_number():
    """If itemprop/pd__part-number is missing, PS number is extracted from the URL."""
    html = "<html><body><h1 class='title-lg'>Water Filter</h1></body></html>"
    part = _parse_part_detail(html, "https://www.partselect.com/PS11752778-Some-Part.htm", "refrigerator")
    assert part is not None
    assert part["part_number"] == "PS11752778"


def test_parse_returns_none_for_missing_part_number():
    """No PS number in HTML or URL → returns None (skip the record)."""
    part = _parse_part_detail(INVALID_PART_HTML, "https://www.partselect.com/about", "refrigerator")
    assert part is None


# ─── unit: _discover_part_urls ────────────────────────────────────────────────


def test_discover_finds_ps_links():
    urls = _discover_part_urls(CATEGORY_HTML, "https://www.partselect.com/Refrigerator-Parts.htm")
    assert len(urls) == 3
    assert all(re.search(r"/PS\d+", u) for u in urls)


def test_discover_excludes_non_part_links():
    urls = _discover_part_urls(CATEGORY_HTML, "https://www.partselect.com/Refrigerator-Parts.htm")
    assert not any("/about" in u or "/contact" in u for u in urls)


def test_discover_deduplicates_urls():
    html = """
    <html><body>
    <a href="/PS11752778-Part.htm">Part</a>
    <a href="/PS11752778-Part.htm">Part again</a>
    </body></html>
    """
    urls = _discover_part_urls(html, "https://www.partselect.com/Dishwasher-Parts.htm")
    assert len(urls) == 1


def test_discover_strips_query_and_fragment_duplicates():
    """URLs differing only by ?SourceCode=18 or #CustomerReview are the same part."""
    html = """
    <html><body>
    <a href="/PS11752778-Part.htm">Base</a>
    <a href="/PS11752778-Part.htm?SourceCode=18">With query</a>
    <a href="/PS11752778-Part.htm#CustomerReview">With fragment</a>
    <a href="/PS11752778-Part.htm?SourceCode=18#Instructions">Both</a>
    </body></html>
    """
    urls = _discover_part_urls(html, "https://www.partselect.com/Refrigerator-Parts.htm")
    assert len(urls) == 1


# ─── unit: _write_part (DB round-trip) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_write_part_round_trip(tmp_path):
    """Written part can be read back from SQLite."""
    from ingestion.build_partselect_index import _apply_schema

    db_path = str(tmp_path / "test.db")
    await _apply_schema(db_path)

    part = _parse_part_detail(
        PART_DETAIL_HTML,
        "https://www.partselect.com/PS11752778.htm",
        "refrigerator",
    )
    await _write_part(db_path, part)

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT part_number, name, price FROM parts WHERE part_number = ?", ("PS11752778",))
        row = await cur.fetchone()
        assert row is not None
        assert row[0] == "PS11752778"
        assert row[1] == "Refrigerator Water Filter"
        assert "$24.99" in row[2]

        cur = await db.execute("SELECT model_number FROM part_compatibility WHERE part_number = ?", ("PS11752778",))
        models = [r[0] for r in await cur.fetchall()]
        assert "WRS325FDAM04" in models

        cur = await db.execute("SELECT step_text FROM part_installation_steps WHERE part_number = ? ORDER BY step_index", ("PS11752778",))
        steps = [r[0] for r in await cur.fetchall()]
        assert len(steps) == 2

        cur = await db.execute("SELECT symptom_key FROM part_symptoms WHERE part_number = ?", ("PS11752778",))
        symptoms = [r[0] for r in await cur.fetchall()]
        assert len(symptoms) == 3


# ─── live tests (require Playwright + internet) ───────────────────────────────


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_category_page_returns_part_urls():
    """Crawl4AI can fetch a PartSelect category page and we find PS-number links."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=60_000,
        magic=True,
        js_code="""
const maxWait = 6000, step = 400;
let waited = 0;
while (waited < maxWait) {
  const hasModels = document.querySelector('.pd__crossref__part a, .js-modelsList a');
  const hasStories = document.querySelector('.repair-story__title');
  if (hasModels && hasStories) break;
  await new Promise(r => setTimeout(r, step));
  waited += step;
}
""",
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(
            url="https://www.partselect.com/Refrigerator-Parts.htm",
            config=config,
        )

    assert result.success, f"Crawl4AI failed to fetch category page: {result.error_message}"
    urls = _discover_part_urls(result.html, "https://www.partselect.com/Refrigerator-Parts.htm")
    assert len(urls) > 0, "No PS-number part URLs found on category page"


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_known_part_page_parses():
    """Crawl4AI fetches PS11752778 and the parser extracts the correct part number."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    url = "https://www.partselect.com/PS11752778-Whirlpool-W10295370A-Refrigerator-Water-Filter.htm"
    config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=60_000,
        magic=True,
        js_code="""
const maxWait = 6000, step = 400;
let waited = 0;
while (waited < maxWait) {
  const hasModels = document.querySelector('.pd__crossref__part a, .js-modelsList a');
  const hasStories = document.querySelector('.repair-story__title');
  if (hasModels && hasStories) break;
  await new Promise(r => setTimeout(r, step));
  waited += step;
}
""",
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=url, config=config)

    assert result.success, f"Crawl4AI failed to fetch part page: {result.error_message}"

    part = _parse_part_detail(result.html, url, "refrigerator")
    assert part is not None, "Parser returned None — page HTML didn't match any selector"
    assert part["part_number"] == "PS11752778"
    assert part["name"], "Name is empty"
    assert part["price"], "Price is empty"


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_part_page_has_compatible_models():
    """A known high-compatibility part returns a non-empty compatible_models list."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    # PS11752778 is compatible with many Whirlpool fridge models
    url = "https://www.partselect.com/PS11752778-Whirlpool-W10295370A-Refrigerator-Water-Filter.htm"
    config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=60_000,
        magic=True,
        js_code="""
const maxWait = 6000, step = 400;
let waited = 0;
while (waited < maxWait) {
  const hasModels = document.querySelector('.pd__crossref__part a, .js-modelsList a');
  const hasStories = document.querySelector('.repair-story__title');
  if (hasModels && hasStories) break;
  await new Promise(r => setTimeout(r, step));
  waited += step;
}
""",
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=url, config=config)

    assert result.success
    part = _parse_part_detail(result.html, url, "refrigerator")
    assert part is not None
    # Dump HTML around "compatible" or "model" to help diagnose selector misses
    import re as _re
    matches = _re.findall(r'.{0,200}(?:compatible|crossref|modelsList).{0,200}', result.html, _re.I)
    debug = "\n".join(matches[:5]) or result.html[2000:4000]
    assert len(part["compatible_models"]) > 0, (
        "No compatible models extracted — selector may be wrong.\n"
        "Relevant HTML snippets:\n" + debug
    )


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_full_ingest_one_part(tmp_path):
    """End-to-end: fetch a real part, write to DB, read it back."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    from ingestion.build_partselect_index import _apply_schema

    db_path = str(tmp_path / "live_test.db")
    await _apply_schema(db_path)

    url = "https://www.partselect.com/PS11752778-Whirlpool-W10295370A-Refrigerator-Water-Filter.htm"
    config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=60_000,
        magic=True,
        js_code="""
const maxWait = 6000, step = 400;
let waited = 0;
while (waited < maxWait) {
  const hasModels = document.querySelector('.pd__crossref__part a, .js-modelsList a');
  const hasStories = document.querySelector('.repair-story__title');
  if (hasModels && hasStories) break;
  await new Promise(r => setTimeout(r, step));
  waited += step;
}
""",
    )
    async with AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False)) as crawler:
        result = await crawler.arun(url=url, config=config)

    assert result.success
    part = _parse_part_detail(result.html, url, "refrigerator")
    assert part is not None
    await _write_part(db_path, part)

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT part_number, name FROM parts WHERE part_number = 'PS11752778'")
        row = await cur.fetchone()
        assert row is not None, "Part was not written to DB"
        assert row[0] == "PS11752778"
        assert row[1], "Name was not written"
