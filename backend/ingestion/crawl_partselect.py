"""
Offline batch ingestion: crawl PartSelect category pages using Crawl4AI.

Crawl4AI uses a Playwright-backed browser - Chromium, which avoids the 403s that plain httpx gets from PartSelect. 
HTML is fetched by the browser and then parsed with BeautifulSoup using deterministic CSS selectors.

Strategy
--------
1. Fetch Dishwasher and Refrigerator category pages to discover part URLs
   (looks for links matching /PS{number} in the rendered HTML).
2. For each part URL (up to --limit per category), fetch the detail page and
   parse it into structured fields.
3. Write parts + compatibility + installation steps + symptom tags to SQLite.

Prerequisites
-------------
    pip install crawl4ai
    playwright install chromium   # one-time browser setup

Usage
-----
    cd backend
    python -m ingestion.crawl_partselect --limit 50
    python -m ingestion.crawl_partselect --limit 100 --concurrency 3 --db-path partselect_index.db
"""
from __future__ import annotations

import asyncio
import argparse
import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import aiosqlite
from bs4 import BeautifulSoup

from config import INDEX_DB_PATH
from index.structured_store import normalize_symptom_key
from ingestion.build_partselect_index import _apply_schema

logger = logging.getLogger(__name__)

BASE_URL = "https://www.partselect.com"

CATEGORY_URLS = [
    (f"{BASE_URL}/Dishwasher-Parts.htm", "dishwasher"),
    (f"{BASE_URL}/Refrigerator-Parts.htm", "refrigerator"),
]

# ─── parsing ──────────────────────────────────────────────────────────────────


def _parse_part_detail(html: str, url: str, appliance_type: str) -> Optional[dict]:
    """Parse a PartSelect part detail page into a structured dict.

    Returns None if the page doesn't look like a valid part page.
    """
    soup = BeautifulSoup(html, "html.parser")

    # ── Part number (PS number) ──────────────────────────────────────────────
    part_number = ""
    # itemprop is the most reliable signal
    for sel in ["span[itemprop='productID']", ".pd__part-number"]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            # Strip label prefix like "PartSelect #" or "Part #"
            text = re.sub(r"^[A-Za-z\s#:]+", "", text).strip()
            if text.startswith("PS") or re.match(r"PS\d+", text, re.I):
                part_number = text.upper()
                break
    if not part_number:
        # Fallback: pull PS-number directly from the URL
        m = re.search(r"/(PS\d+)", url, re.IGNORECASE)
        if m:
            part_number = m.group(1).upper()
    if not part_number:
        return None

    # ── Name ────────────────────────────────────────────────────────────────
    name = ""
    for sel in ["h1.title-lg", "h1"]:
        el = soup.select_one(sel)
        if el:
            name = el.get_text(strip=True)
            break

    # ── Price ────────────────────────────────────────────────────────────────
    price = ""
    for sel in [
        "span.js-partPrice",
        "span.price.pd__price",
        ".price",
        "[itemprop='price']",
    ]:
        el = soup.select_one(sel)
        if el:
            price = el.get_text(strip=True)
            if price:
                break

    # ── In-stock ─────────────────────────────────────────────────────────────
    in_stock = False
    for sel in [".pd__availability", ".js-inventory-message", "[itemprop='availability']"]:
        el = soup.select_one(sel)
        if el and "in stock" in el.get_text(strip=True).lower():
            in_stock = True
            break

    # ── Description ──────────────────────────────────────────────────────────
    description = ""
    for sel in [".pd__description", "[itemprop='description']"]:
        el = soup.select_one(sel)
        if el:
            description = el.get_text(strip=True)
            break

    # ── Manufacturer part number ──────────────────────────────────────────────
    mfr_number = None
    # itemprop='mpn' contains only the value — no label stripping needed
    mpn_el = soup.select_one("span[itemprop='mpn']")
    if mpn_el:
        mfr_number = mpn_el.get_text(strip=True) or None
    if not mfr_number:
        # .pd__mfr-number wraps "Manufacturer Part Number <value>" — take last span
        mfr_el = soup.select_one(".pd__mfr-number")
        if mfr_el:
            spans = mfr_el.select("span")
            if len(spans) >= 2:
                mfr_number = spans[-1].get_text(strip=True) or None
            elif spans:
                mfr_number = spans[0].get_text(strip=True) or None

    # ── Brand ─────────────────────────────────────────────────────────────────
    brand = None
    brand_el = soup.select_one("span[itemprop='brand'] span[itemprop='name']")
    if brand_el:
        brand = brand_el.get_text(strip=True) or None

    # ── Availability ──────────────────────────────────────────────────────────
    availability = None
    for sel in ["span[itemprop='availability']", ".pd__availability"]:
        el = soup.select_one(sel)
        if el:
            availability = el.get_text(strip=True) or None
            if availability:
                break
    in_stock = "in stock" in (availability or "").lower() if availability else in_stock

    # ── Install difficulty + time ─────────────────────────────────────────────
    install_difficulty = None
    install_time = None
    install_container = soup.select_one("div.flex-lg-grow-1.justify-content-lg-between")
    if install_container:
        paras = install_container.select("p")
        if len(paras) >= 1:
            install_difficulty = paras[0].get_text(strip=True) or None
        if len(paras) >= 2:
            install_time = paras[1].get_text(strip=True) or None

    # ── Appliance type (works-with section) ───────────────────────────────────
    appliance_type_scraped = None
    for col in soup.select("div.col-md-6.mt-3"):
        header = col.select_one("h2, h3, strong")
        if header and "works with" in header.get_text(strip=True).lower():
            appliance_type_scraped = col.get_text(strip=True)[:200] or None
            break

    # ── Replaces parts ────────────────────────────────────────────────────────
    replace_parts = None
    for sel in ["div[data-collapse-container]"]:
        el = soup.select_one(sel)
        if el and "replac" in el.get_text(strip=True).lower():
            nums = re.findall(r"\b[A-Z]{1,3}\d{5,12}\b", el.get_text())
            if nums:
                replace_parts = ", ".join(nums[:20])
            break
    if not replace_parts:
        # Scan all text for "replaces" sections
        for el in soup.select("section, div"):
            txt = el.get_text(strip=True)
            if txt.lower().startswith("replaces") or "this part replaces" in txt.lower():
                nums = re.findall(r"\b[A-Z]{1,3}\d{5,12}\b", txt)
                if nums:
                    replace_parts = ", ".join(nums[:20])
                    break

    # ── Symptoms (structured, from "fixes the following symptoms" section) ─────
    symptoms_text = None
    for col in soup.select("div.col-md-6.mt-3"):
        header = col.select_one("h2, h3, strong")
        if header and "fixes the following symptoms" in header.get_text(strip=True).lower():
            items = [li.get_text(strip=True) for li in col.select("li")]
            if items:
                symptoms_text = "; ".join(items[:20])
            break

    # ── Repair rating ─────────────────────────────────────────────────────────
    repair_rating = None
    rating_el = soup.select_one("span[itemprop='ratingValue']")
    count_el = soup.select_one("meta[itemprop='reviewCount']")
    if rating_el:
        rating_val = rating_el.get_text(strip=True)
        count_val = count_el.get("content", "") if count_el else ""
        repair_rating = f"{rating_val} / 5.0" + (f", {count_val} reviews" if count_val else "")

    # ── Symptoms ─────────────────────────────────────────────────────────────
    # PartSelect surfaces symptoms through user repair story titles
    # (e.g., "Dishes were not drying properly", "Heat element was cracked").
    symptoms: list[str] = []
    seen_sym: set[str] = set()
    for sym_el in soup.select(".repair-story__title"):
        text = sym_el.get_text(strip=True)
        if text and len(text) > 3:
            key = normalize_symptom_key(text)
            if key not in seen_sym:
                seen_sym.add(key)
                symptoms.append(key)

    # ── Compatible models ─────────────────────────────────────────────────────
    compatible_models: list[str] = []
    seen_models: set[str] = set()
    for sel in [
        ".pd__crossref__part a",   # inner items once AJAX loads
        "#ModelCrossReference ~ div a",
        ".js-modelsList a",
        ".pd__crossref__model a",
        "#compatible-models .pd__crossref__part a",
    ]:
        for a in soup.select(sel):
            mn = a.get_text(strip=True).upper()
            if mn and mn not in seen_models:
                seen_models.add(mn)
                compatible_models.append(mn)
    # Fallback: table rows that look like model numbers
    if not compatible_models:
        for td in soup.select("td.bold, td.modelNum"):
            mn = td.get_text(strip=True).upper()
            if re.match(r"[A-Z0-9]{5,20}", mn) and mn not in seen_models:
                seen_models.add(mn)
                compatible_models.append(mn)

    # Cap to avoid bloating the DB for parts with hundreds of compatible models
    compatible_models = compatible_models[:500]

    # ── Installation steps ────────────────────────────────────────────────────
    # PartSelect stores user repair narratives in .repair-story__instruction.
    # These are paragraph-form instructions, not numbered steps; we store each
    # as a separate "step" so the DB schema is satisfied.
    installation_steps: list[str] = []
    for el in soup.select(".repair-story__instruction"):
        text = el.get_text(strip=True)
        if text and len(text) > 20:
            installation_steps.append(text[:500])  # cap per-narrative length

    return {
        "part_number": part_number,
        "name": name,
        "price": price,
        "in_stock": in_stock,
        "description": description,
        "manufacturer_part_number": mfr_number,
        "source_url": url,
        "symptoms": symptoms,
        "compatible_models": compatible_models,
        "installation_steps": installation_steps,
        "appliance_type": appliance_type,
        "brand": brand,
        "availability": availability,
        "appliance_type_scraped": appliance_type_scraped,
        "install_difficulty": install_difficulty,
        "install_time": install_time,
        "replace_parts": replace_parts,
        "symptoms_text": symptoms_text,
        "repair_rating": repair_rating,
    }


def _normalize_part_url(url: str) -> str:
    """Strip query string and fragment from a part URL to get the canonical form."""
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def _discover_part_urls(html: str, base_url: str) -> list[str]:
    """Extract unique part detail URLs from a category/listing page.

    Deduplicates on the canonical URL (no query string, no fragment) so that
    variants like ?SourceCode=18#CustomerReview don't produce redundant fetches.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    urls: list[str] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        full_url = _normalize_part_url(urljoin(base_url, href))
        if (
            re.search(r"/PS\d+", full_url, re.IGNORECASE)
            and full_url not in seen
            and BASE_URL in full_url
        ):
            seen.add(full_url)
            urls.append(full_url)
    return urls


# ─── DB writes ────────────────────────────────────────────────────────────────


async def _part_exists(db_path: str, part_number: str) -> bool:
    """Return True if the part is already in the DB."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT 1 FROM parts WHERE part_number = ?", (part_number,))
        row = await cur.fetchone()
        await cur.close()
        return row is not None


async def _help_chunk_exists(db_path: str, chunk_id: str) -> bool:
    """Return True if the help chunk is already in the DB."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT 1 FROM help_chunks WHERE chunk_id = ?", (chunk_id,))
        row = await cur.fetchone()
        await cur.close()
        return row is not None


async def _write_help_chunk(db_path: str, chunk: dict) -> None:
    """Write a single help chunk + FTS entry to the DB."""
    ts = time.time()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO help_chunks
              (chunk_id, appliance_type, help_type, symptom_key, source_url, chunk_text, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk["chunk_id"],
                chunk["appliance_type"],
                chunk["help_type"],
                chunk["symptom_key"],
                chunk["source_url"],
                chunk["chunk_text"],
                ts,
            ),
        )
        await db.execute(
            "INSERT OR REPLACE INTO help_chunks_fts (chunk_id, chunk_text) VALUES (?, ?)",
            (chunk["chunk_id"], chunk["chunk_text"]),
        )
        await db.commit()


async def _write_part(db_path: str, part: dict) -> None:
    pn = part["part_number"]
    ts = time.time()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO parts (
              part_number, name, price, in_stock, description,
              manufacturer_part_number, source_url, updated_at,
              brand, availability, appliance_type,
              install_difficulty, install_time, replace_parts,
              symptoms_text, repair_rating
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pn, part["name"], part["price"],
                1 if part["in_stock"] else 0,
                part["description"], part["manufacturer_part_number"],
                part["source_url"], ts,
                part.get("brand"),
                part.get("availability"),
                part.get("appliance_type_scraped") or part.get("appliance_type"),
                part.get("install_difficulty"),
                part.get("install_time"),
                part.get("replace_parts"),
                part.get("symptoms_text"),
                part.get("repair_rating"),
            ),
        )
        # FTS index
        await db.execute(
            "INSERT OR REPLACE INTO parts_fts (part_number, name, description) VALUES (?, ?, ?)",
            (pn, part["name"], part["description"]),
        )

        for mn in part["compatible_models"]:
            await db.execute(
                "INSERT OR IGNORE INTO models (model_number, appliance_type, updated_at) VALUES (?, ?, ?)",
                (mn, part["appliance_type"], ts),
            )
            await db.execute(
                """
                INSERT OR REPLACE INTO part_compatibility
                  (part_number, model_number, evidence_url, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (pn, mn, part["source_url"], ts),
            )

        for i, step in enumerate(part["installation_steps"]):
            await db.execute(
                """
                INSERT OR REPLACE INTO part_installation_steps
                  (part_number, step_index, step_text, evidence_url, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (pn, i, step, part["source_url"], ts),
            )

        for symptom_key in part["symptoms"]:
            await db.execute(
                """
                INSERT OR REPLACE INTO part_symptoms
                  (part_number, symptom_key, evidence_url, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (pn, symptom_key, part["source_url"], ts),
            )

        await db.commit()


# ─── main crawl loop ──────────────────────────────────────────────────────────


async def crawl_and_ingest(
    db_path: str,
    limit_per_category: int,
    concurrency: int,
) -> None:
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    except ImportError:
        raise SystemExit(
            "crawl4ai is not installed.\n"
            "Run: pip install crawl4ai && playwright install chromium"
        )

    await _apply_schema(db_path)

    browser_config = BrowserConfig(headless=True, verbose=False)
    # domcontentloaded is reliable on PartSelect — networkidle times out because
    # the page keeps firing analytics/tracking requests indefinitely.
    # js_code adds a 2s pause after DOM load to let lazy-rendered sections
    # (compatible models, symptoms) finish populating before we capture HTML.
    # magic=True enables Crawl4AI's stealth mode to avoid bot detection.
    run_config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=60_000,
        magic=True,
        # Poll until the lazy-loaded ModelCrossReference AJAX section populates,
        # then proceed immediately. Falls through after 6s if it never appears
        # (parts with no compatible models).
        js_code="""
// Scroll to models section to trigger lazy-load
const modelSection = document.querySelector('#ModelCrossReference, [data-tab="models"]');
if (modelSection) modelSection.scrollIntoView();

const maxWait = 10000, step = 500;
let waited = 0, lastCount = 0;
while (waited < maxWait) {
  const models = document.querySelectorAll('.pd__crossref__part a, .js-modelsList a');
  const hasStories = document.querySelector('.repair-story__title');
  if (models.length > 0 && models.length === lastCount && hasStories) break;
  lastCount = models.length;
  await new Promise(r => setTimeout(r, step));
  waited += step;
}
""",
    )

    all_part_urls: list[tuple[str, str]] = []

    async with AsyncWebCrawler(config=browser_config) as crawler:
        # ── Step 1: discover part URLs from each category page ────────────────
        for cat_url, appliance_type in CATEGORY_URLS:
            logger.info("Discovering %s parts from %s", appliance_type, cat_url)
            result = await crawler.arun(url=cat_url, config=run_config)
            if not result.success:
                logger.warning("Failed to fetch category page %s", cat_url)
                continue
            urls = _discover_part_urls(result.html, cat_url)
            logger.info("  Found %d part URLs (keeping up to %d)", len(urls), limit_per_category)
            all_part_urls.extend(
                (u, appliance_type) for u in urls[:limit_per_category]
            )

        if not all_part_urls:
            logger.error("No part URLs discovered — aborting.")
            return

        logger.info("Total parts to ingest: %d", len(all_part_urls))

        # ── Step 2: fetch + index each part with bounded concurrency ──────────
        sem = asyncio.Semaphore(concurrency)
        stats = {"ok": 0, "fail": 0}

        async def _ingest_one(url: str, appliance_type: str) -> None:
            async with sem:
                try:
                    # Skip if already indexed — PS number is in the URL
                    m = re.search(r"/(PS\d+)", url, re.IGNORECASE)
                    if m and await _part_exists(db_path, m.group(1).upper()):
                        logger.debug("Skipping already-indexed part: %s", m.group(1).upper())
                        stats["ok"] += 1
                        return
                    result = await crawler.arun(url=url, config=run_config)
                    if not result.success:
                        logger.warning("Fetch failed: %s", url)
                        stats["fail"] += 1
                        return
                    part = _parse_part_detail(result.html, url, appliance_type)
                    if part is None:
                        logger.warning("Parse failed (no PS number): %s", url)
                        stats["fail"] += 1
                        return
                    await _write_part(db_path, part)
                    logger.info(
                        "[%s] %s — %s",
                        appliance_type,
                        part["part_number"],
                        part["name"][:50] or "(no name)",
                    )
                    stats["ok"] += 1
                except Exception as exc:
                    logger.error("Error ingesting %s: %s", url, exc)
                    stats["fail"] += 1

        await asyncio.gather(*(_ingest_one(u, a) for u, a in all_part_urls))
        logger.info("Parts: indexed %d, failed %d", stats["ok"], stats["fail"])

    # ── Step 3: scrape repair guide pages into help_chunks ────────────────────
    logger.info("Scraping repair guide pages into help_chunks...")
    guide_count = await scrape_and_ingest_repair_guides(
        db_path=db_path, concurrency=concurrency
    )
    logger.info(
        "Done. Parts: %d indexed, %d failed. Repair guides: %d indexed.",
        stats["ok"], stats["fail"], guide_count,
    )


def _parse_repair_guide(html: str, url: str, appliance_type: str, slug: str) -> Optional[dict]:
    """Parse a PartSelect repair guide detail page into a help_chunk dict."""
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title = ""
    for sel in ["h1.title-lg", "h1"]:
        el = soup.select_one(sel)
        if el:
            title = el.get_text(strip=True)
            break

    # Gather paragraph/list content from the main content area, with fallback
    content_lines: list[str] = []
    content_root = None
    for sel in [".main-content", "main", "article", ".repair-guide", ".content-body"]:
        content_root = soup.select_one(sel)
        if content_root:
            break
    if content_root is None:
        content_root = soup

    for el in content_root.select("p, li, .symptom-description, .repair-guide__description"):
        text = el.get_text(strip=True)
        if text and len(text) > 20:
            content_lines.append(text)
        if len(content_lines) >= 12:
            break

    # PS part numbers mentioned anywhere on the page
    ps_numbers = sorted(
        {m.group(0).upper() for m in re.finditer(r"\bPS\d{6,10}\b", soup.get_text())}
    )

    chunk_parts: list[str] = []
    if title:
        chunk_parts.append(title)
    chunk_parts.extend(content_lines)
    if ps_numbers:
        chunk_parts.append("Related parts: " + ", ".join(ps_numbers))

    chunk_text = "\n".join(chunk_parts).strip()
    if not chunk_text:
        chunk_text = f"{appliance_type} repair guide: {slug.replace('-', ' ')}"

    # Symptom key: "Not-Making-Ice" → "not making ice"
    symptom_key = normalize_symptom_key(slug.replace("-", " "))

    return {
        "chunk_id": f"repair_guide_{appliance_type}_{slug.lower()}",
        "appliance_type": appliance_type,
        "help_type": "repair_guide",
        "symptom_key": symptom_key,
        "source_url": url,
        "chunk_text": chunk_text[:2000],
    }


async def scrape_and_ingest_repair_guides(
    db_path: str,
    concurrency: int = 3,
) -> int:
    """Fetch PartSelect repair guide pages and write them to help_chunks.

    1. Fetches /Repair/Refrigerator/ and /Repair/Dishwasher/ with httpx to
       discover all symptom guide URLs (static HTML — no browser needed).
    2. Fetches each guide's detail page with Crawl4AI and extracts content.
    3. Writes each guide as a help_chunk so diagnose_troubleshooting() can
       cite verified URLs instead of hardcoded ones.

    Returns the number of guides indexed.
    """
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    except ImportError:
        logger.warning("crawl4ai not available — skipping repair guide ingestion")
        return 0

    REPAIR_INDEXES = [
        (f"{BASE_URL}/Repair/Refrigerator/", "refrigerator"),
        (f"{BASE_URL}/Repair/Dishwasher/", "dishwasher"),
    ]

    browser_config = BrowserConfig(headless=True, verbose=False)
    index_run_config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=30_000,
        magic=True,
    )
    guide_urls: list[tuple[str, str, str]] = []  # (url, appliance_type, slug)
    indexed = 0
    sem = asyncio.Semaphore(concurrency)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Step 1: Discover guide URLs using the browser (httpx gets 403)
        for index_url, appliance_type in REPAIR_INDEXES:
            result = await crawler.arun(url=index_url, config=index_run_config)
            if not result.success:
                logger.warning("Could not fetch repair index %s", index_url)
                continue

            # Brand names appear as sub-paths on the dishwasher index but are not
            # symptom guides — exclude slugs that are single capitalised words (brands).
            BRAND_SLUGS = {
                "Amana", "Bosch", "Frigidaire", "GE", "Kenmore", "Kitchenaid",
                "LG", "Maytag", "Samsung", "Whirlpool",
            }
            soup = BeautifulSoup(result.html, "html.parser")
            seen_slugs: set[str] = set()
            for a in soup.find_all("a", href=True):
                href = str(a["href"])
                full = urljoin(BASE_URL, href)
                if re.match(
                    rf"https://www\.partselect\.com/Repair/{appliance_type.capitalize()}/[^/]+/$",
                    full,
                    re.IGNORECASE,
                ):
                    slug = full.rstrip("/").rsplit("/", 1)[-1]
                    if slug in BRAND_SLUGS or slug in seen_slugs:
                        continue
                    seen_slugs.add(slug)
                    guide_urls.append((full, appliance_type, slug))

            logger.info("Found %d repair guide URLs for %s", len(seen_slugs), appliance_type)

        if not guide_urls:
            logger.warning("No repair guide URLs discovered — skipping")
            return 0

        logger.info("Fetching %d repair guide detail pages", len(guide_urls))
        async def _ingest_guide(url: str, appliance_type: str, slug: str) -> None:
            nonlocal indexed
            async with sem:
                try:
                    chunk_id = f"repair_guide_{appliance_type}_{slug.lower()}"
                    if await _help_chunk_exists(db_path, chunk_id):
                        logger.debug("Skipping already-indexed repair guide: %s", chunk_id)
                        indexed += 1
                        return
                    result = await crawler.arun(url=url, config=index_run_config)
                    if not result.success:
                        logger.warning("Failed to fetch repair guide: %s", url)
                        return
                    chunk = _parse_repair_guide(result.html, url, appliance_type, slug)
                    if chunk:
                        await _write_help_chunk(db_path, chunk)
                        logger.info("[repair_guide] %s/%s", appliance_type, slug)
                        indexed += 1
                except Exception as exc:
                    logger.error("Error ingesting repair guide %s: %s", url, exc)

        await asyncio.gather(*(_ingest_guide(u, a, s) for u, a, s in guide_urls))

    logger.info("Indexed %d repair guides into help_chunks", indexed)
    return indexed


async def scrape_repair_guide_urls() -> dict[str, dict[str, str]]:
    """Fetch the PartSelect repair index pages and return verified symptom→URL mappings.

    Returns a dict keyed by appliance_type → {symptom_slug: url}.
    Uses httpx (no browser needed — repair index pages are static HTML).
    """
    import httpx

    REPAIR_INDEXES = {
        "refrigerator": f"{BASE_URL}/Repair/Refrigerator/",
        "dishwasher": f"{BASE_URL}/Repair/Dishwasher/",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    results: dict[str, dict[str, str]] = {}
    async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
        for appliance, index_url in REPAIR_INDEXES.items():
            try:
                resp = await client.get(index_url)
                resp.raise_for_status()
            except Exception as e:
                logger.warning("Could not fetch repair index %s: %s", index_url, e)
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            guides: dict[str, str] = {}
            for a in soup.find_all("a", href=True):
                href = str(a["href"])
                full = urljoin(BASE_URL, href)
                # Repair guide URLs match /Repair/{Appliance}/{Symptom}/
                if re.match(
                    rf"https://www\.partselect\.com/Repair/{appliance.capitalize()}/[^/]+/$",
                    full,
                    re.IGNORECASE,
                ):
                    slug = full.rstrip("/").rsplit("/", 1)[-1].lower()
                    guides[slug] = full

            results[appliance] = guides
            logger.info("Found %d repair guide URLs for %s", len(guides), appliance)

    return results


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl PartSelect and build the structured SQLite index."
    )
    parser.add_argument(
        "--db-path", default=INDEX_DB_PATH,
        help="Path to the SQLite index DB",
    )
    parser.add_argument(
        "--limit", type=int, default=50,
        help="Max part URLs to ingest per category (default: 50)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=3,
        help="Number of concurrent browser pages (default: 3)",
    )
    parser.add_argument(
        "--verify-repair-urls", action="store_true",
        help="Fetch repair guide index pages and print verified symptom→URL mappings",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.verify_repair_urls:
        urls = await scrape_repair_guide_urls()
        import json as _json
        print(_json.dumps(urls, indent=2))
        return

    await crawl_and_ingest(
        db_path=args.db_path,
        limit_per_category=args.limit,
        concurrency=args.concurrency,
    )


if __name__ == "__main__":
    asyncio.run(main())
