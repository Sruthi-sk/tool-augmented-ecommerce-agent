"""
KnowledgeService: high-level abstraction used by tools.

Tools should not coordinate multiple retrieval backends. Instead:
- Tools call KnowledgeService.
- KnowledgeService merges structured facts (StructuredStore) with semantic help
  (HelpVectorIndex) deterministically.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from functools import lru_cache
from typing import Any, Optional

import aiosqlite

from config import INDEX_DB_PATH
from index.help_vector_store import HelpVectorIndex
from index.structured_store import StructuredStore
from index.structured_store import normalize_symptom_key

logger = logging.getLogger(__name__)

# ── Live compatibility cache ─────────────────────────────────────────────────
# Keyed by (part_number_upper, model_number_upper).  Avoids re-spawning a
# browser for the same (part, model) pair within a process lifetime.
# An asyncio.Lock serialises concurrent requests for the *same* key so only
# one browser runs.
_compat_cache: dict[tuple[str, str], dict] = {}
_compat_locks: dict[tuple[str, str], asyncio.Lock] = {}
_compat_global_lock = asyncio.Lock()  # guards _compat_locks dict creation

COMPAT_CACHE_MAX = 1024  # evict oldest when exceeded


class KnowledgeService:
    def __init__(
        self,
        structured_store: StructuredStore,
        help_vector_index: HelpVectorIndex,
        # Optional: a cache can be injected later (Phase 0 avoids changing runtime).
        query_cache: Optional[Any] = None,
    ):
        self._structured_store = structured_store
        self._help_vector_index = help_vector_index
        self._query_cache = query_cache

    async def search_parts(
        self, query: str, appliance_type: str, model_number: Optional[str] = None
    ) -> dict:
        parts = await self._structured_store.search_parts(
            query=query, appliance_type=appliance_type, model_number=model_number
        )

        live_scraped = False
        # Live fallback: if local DB returned 0 results and we have a model number,
        # scrape the PartSelect model parts page for matches.
        if not parts and model_number:
            logger.info("Local DB miss for query=%r model=%s — trying live scrape", query, model_number)
            parts = await _scrape_model_parts(model_number, query)
            if parts:
                live_scraped = True

        result = {
            "parts": parts,
            "query": query,
            "appliance_type": appliance_type,
            "model_number": model_number or "",
        }
        if live_scraped:
            result["live_scraped"] = True
        return result

    async def lookup_model(self, model_number: str) -> dict:
        """Get model overview — local DB first, live scrape fallback."""
        # Try local DB first
        local = await self._structured_store.get_model_overview(model_number)
        if local and (local.get("parts_count", 0) > 0 or local.get("common_symptoms")):
            return local

        # Fallback: scrape PartSelect model page
        scraped = await _scrape_model_page(model_number)
        if scraped is not None:
            return scraped

        # If local had partial data (model exists but no parts/symptoms), still return it
        if local:
            return local

        return {
            "error": f"Could not retrieve information for model {model_number}.",
            "model_number": model_number,
        }

    async def get_part_details(self, part_number: str) -> dict:
        part = await self._structured_store.get_part_details(part_number)
        if part is None:
            return {"error": f"Part {part_number} not found.", "part_number": part_number}
        return part

    async def check_compatibility(self, part_number: str, model_number: str) -> dict:
        mn = (model_number or "").strip()

        # Reject obviously invalid model numbers before hitting live check.
        # Real appliance model numbers are 5–15 characters.
        if len(mn) > 15 or len(mn) < 3:
            search_url = f"https://www.partselect.com/searchsuggestions/?term={mn}&SourceCode=42"
            help_url = "https://www.partselect.com/Find-Your-Model-Number/"
            return {
                "compatible": None,
                "part_number": part_number,
                "part_name": "",
                "model_number": model_number,
                "compatible_models_count": 0,
                "source_url": "",
                "model_not_found": True,
                "similar_models_url": search_url,
                "find_model_help_url": help_url,
                "note": (
                    f"The model number \"{mn}\" doesn't look like a valid appliance model number. "
                    f"Please double-check your model number."
                    f"\n\n[Search for similar models]({search_url})"
                    f"\n\n[Need help finding your model number?]({help_url})"
                ),
            }

        result = await self._structured_store.check_compatibility(
            part_number=part_number, model_number=model_number
        )

        # If local DB returned a definitive answer, use it
        if result.get("compatible") is not None:
            return result

        # Local index miss — fall back to live PartSelect compatibility widget
        source_url = result.get("source_url", "")
        if not source_url:
            return result

        try:
            live = await _cached_live_compatibility_check(source_url, part_number, model_number)
        except Exception as exc:
            logger.warning("Live compatibility check failed: %s", exc)
            return result

        if live is None or live.get("compatible") is None:
            # Build a helpful response for any indeterminate compatibility result
            resp_unknown = {
                "compatible": None,
                "part_number": part_number,
                "part_name": result.get("part_name", ""),
                "model_number": model_number,
                "compatible_models_count": result.get("compatible_models_count", 0),
                "source_url": source_url,
            }

            similar_url = (live or {}).get("similar_models_url", "")
            help_url = (live or {}).get("find_model_help_url", "")
            model_not_found = live and live.get("model_not_found")
            search_url = f"https://www.partselect.com/Models/{model_number}/?SourceCode=42"

            if model_not_found:
                resp_unknown["model_not_found"] = True
                if similar_url:
                    resp_unknown["similar_models_url"] = similar_url
                if help_url:
                    resp_unknown["find_model_help_url"] = help_url
                resp_unknown["note"] = (
                    f"We couldn't find an exact match for model {model_number} on PartSelect. "
                    f"Please double-check your model number."
                    + (f"\n\n[Search for similar models]({similar_url})" if similar_url else "")
                    + (f"\n\n[Need help finding your model number?]({help_url})" if help_url else "")
                )
            else:
                # Live scraping failed (PartSelect bot detection / 403)
                part_url = result.get("source_url", "")
                resp_unknown["note"] = (
                    f"Live compatibility check for model {model_number} failed due to "
                    f"PartSelect bot detection. Please check compatibility directly on PartSelect.\n\n"
                    + (f"[Check compatibility on PartSelect]({part_url})" if part_url else f"[Search on PartSelect]({search_url})")
                )
                resp_unknown["model_details_url"] = part_url or search_url

            return resp_unknown

        is_compatible = live["compatible"]

        # Persist compatible results into SQLite for future local-index hits
        pn = part_number.upper()
        mn = model_number.upper()
        try:
            db_path = self._structured_store._db_path
            async with aiosqlite.connect(db_path) as db:
                if is_compatible:
                    await db.execute(
                        "INSERT OR IGNORE INTO models (model_number, updated_at) VALUES (?, ?)",
                        (mn, time.time()),
                    )
                    await db.execute(
                        """INSERT OR REPLACE INTO part_compatibility
                           (part_number, model_number, evidence_url, updated_at)
                           VALUES (?, ?, ?, ?)""",
                        (pn, mn, source_url, time.time()),
                    )
                    await db.commit()
        except Exception as exc:
            logger.warning("Failed to persist compatibility result: %s", exc)

        resp = {
            "compatible": is_compatible,
            "part_number": part_number,
            "part_name": result.get("part_name", ""),
            "model_number": model_number,
            "compatible_models_count": result.get("compatible_models_count", 0),
            "source_url": source_url,
            "live_checked": True,
        }

        # Include model description (e.g. "Kenmore Refrigerator") if extracted
        model_description = live.get("model_description", "")
        if model_description:
            resp["model_description"] = model_description

        # Include model details link
        model_details_url = live.get("model_details_url", "")
        if model_details_url:
            resp["model_details_url"] = model_details_url

        if is_compatible:
            note_parts = []
            if model_description:
                note_parts.append(f"Your {model_description} (model {model_number}) is confirmed compatible.")
            if model_details_url:
                note_parts.append(f"[View model details]({model_details_url})")
            if note_parts:
                resp["note"] = " ".join(note_parts)
        elif not is_compatible and model_details_url:
            desc_label = f"your {model_description} ({model_number})" if model_description else model_number
            resp["note"] = (
                f"This part is not compatible with {desc_label}. "
                f"[Browse all parts for your model]({model_details_url})"
            )

        return resp

    async def get_installation_guide(self, part_number: str) -> dict:
        """
        Structured-first installation behavior:
        - If indexed steps exist, return them.
        - If missing, semantic retrieval may backfill long-form help and deterministically extract steps.
        """
        structured = await self._structured_store.get_installation_steps(part_number)
        if structured.get("error"):
            return structured

        steps = structured.get("steps") or []
        if steps:
            return structured

        # Semantic backfill (Phase 0: likely empty unless help_chunks are populated).
        hits = await self._help_vector_index.search_help(
            query=f"installation {part_number}",
            appliance_type=None,
            help_type="installation_help",
            k=3,
        )
        backfilled_steps = []
        for h in hits:
            txt = h.get("chunk_text") or ""
            # Deterministically extract bullet-like lines as steps.
            for line in txt.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Common step markers: "1.", "-", "*", "Step"
                if re.match(r"^(\d+\.|\-|\*|step\s+\d+)", line, flags=re.IGNORECASE):
                    backfilled_steps.append(line)
                # Fallback: keep short imperative-ish sentences.
                elif len(line) <= 160 and any(w in line.lower() for w in ["turn", "remove", "install", "disconnect", "connect", "replace"]):
                    backfilled_steps.append(line)
                if len(backfilled_steps) >= 8:
                    break
            if len(backfilled_steps) >= 8:
                break

        structured["steps"] = backfilled_steps
        # Prefer PartSelect part source_url if present; otherwise use semantic sources.
        if not structured.get("source_url"):
            structured["source_url"] = hits[0].get("source_url") if hits else ""
        return structured

    async def diagnose_troubleshooting(
        self,
        appliance_type: str,
        symptom: str,
        model_number: str = "",
    ) -> dict:
        """
        Troubleshooting behavior:
        - Structured-first using `troubleshooting_causes`.
        - Semantic backfill may add likely causes or recommended parts when structured data is missing.
        - Service-level canonical output: likely_causes, recommended_parts, source_urls.
        """
        structured = await self._structured_store.get_troubleshooting_causes(
            appliance_type=appliance_type, symptom=symptom
        )
        likely_causes = structured.get("likely_causes") or []
        recommended_parts = structured.get("recommended_parts") or []
        source_urls = structured.get("source_urls") or []
        matched_symptom = structured.get("matched_symptom") or normalize_symptom_key(symptom)

        if likely_causes:
            guide_hits = await self._help_vector_index.search_help(
                query=symptom,
                appliance_type=appliance_type,
                k=5,
            )
            repair_guide_text = guide_hits[0].get("chunk_text") if guide_hits else None
            return {**structured, "repair_guide_text": repair_guide_text}

        # Semantic routing: use FAISS to find the closest symptom_key,
        # then re-query structured causes with that key.
        semantic_hits = await self._help_vector_index.search_help(
            query=symptom,
            appliance_type=appliance_type,
            k=3,
        )
        for hit in semantic_hits:
            semantic_key = hit.get("symptom_key")
            if semantic_key and semantic_key != normalize_symptom_key(symptom):
                routed = await self._structured_store.get_troubleshooting_causes(
                    appliance_type=appliance_type, symptom=semantic_key
                )
                if routed.get("likely_causes"):
                    routed["matched_symptom"] = semantic_key
                    routed["semantic_routed_from"] = symptom
                    guide_hits = await self._help_vector_index.search_help(
                        query=symptom,
                        appliance_type=appliance_type,
                        k=5,
                    )
                    routed["repair_guide_text"] = guide_hits[0].get("chunk_text") if guide_hits else None
                    return routed

        # FTS / semantic backfill for help content when no structured causes exist.
        symptom_key = normalize_symptom_key(symptom)
        hits = await self._help_vector_index.search_help(
            query=symptom,
            appliance_type=appliance_type,
            k=5,
        )
        semantic_text = "\n".join([h.get("chunk_text") or "" for h in hits]).strip()

        # Deterministic normalization:
        # - likely causes: heuristic extraction of lines.
        # - recommended parts: extract PS numbers and de-duplicate.
        # Patterns that indicate navigation chrome, section headers, or procedure
        # steps — not causes. These are common in scraped PartSelect repair pages.
        _SKIP_LINE = re.compile(
            r"^(how\s+to\b"                          # "How to inspect..." / "How To Fix..."
            r"|\d+\s+step"                            # "3 step by step videos"
            r"|unplug\b|disconnect\b|plug\b"          # safety/procedure instructions
            r"|remove\b|install\b|replace\b"
            r"|connect\b|press\b|pull\b|push\b"
            r"|make\s+sure\b|ensure\b|be\s+sure\b"
            r"|looking\s+for\b|visually\s+inspect\b"
            r")",
            re.IGNORECASE,
        )

        likely_causes_backfill: list[dict] = []
        for line in semantic_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if len(likely_causes_backfill) >= 6:
                break
            # Skip lines ending with ":" (section headers) or matching junk patterns
            if line.endswith(":") or _SKIP_LINE.match(line):
                continue
            if re.match(r"^(\-|\*|•)", line) or len(line) < 140:
                likely_causes_backfill.append(
                    {
                        "cause": line.lstrip("-*• ").strip(),
                        "part_type": None,
                        "likelihood": "low",
                    }
                )

        part_numbers = sorted(
            {m.group(0).upper() for m in re.finditer(r"\bPS\d{6,10}\b", semantic_text)}
        )

        source_urls_backfill = [h.get("source_url") for h in hits if h.get("source_url")]

        return {
            "causes": likely_causes_backfill,
            "likely_causes": likely_causes_backfill,
            "recommended_parts": part_numbers,
            "source_urls": source_urls_backfill,
            "matched_symptom": matched_symptom,
            "repair_guide_text": hits[0].get("chunk_text") if hits else None,
        }


async def _scrape_model_page(model_number: str) -> Optional[dict]:
    """Scrape a PartSelect model overview page for headings, symptoms, and sections.

    Returns a dict with model_title, brand, appliance_type, common_symptoms,
    sections, part_categories, and source_url.  Returns None on failure.
    """
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    except ImportError:
        logger.warning("crawl4ai not installed — cannot scrape model page")
        return None

    mn = model_number.strip().upper()
    url = f"https://www.partselect.com/Models/{mn}/"

    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=60_000,
        magic=True,
    )

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)
            if not result.success:
                logger.warning("Failed to fetch model page: %s", url)
                return None

            from bs4 import BeautifulSoup

            soup = BeautifulSoup(result.html, "html.parser")

            # ── Title / brand / appliance type ──────────────────────────
            h1 = soup.find("h1")
            model_title = h1.get_text(strip=True) if h1 else mn
            # Title is typically "10650022211 Kenmore Refrigerator - Overview"
            brand = ""
            appliance_type = ""
            title_clean = model_title.replace(mn, "").strip(" -–—")
            # Remove trailing "- Overview", "- Parts", etc.
            title_clean = re.sub(r"\s*[-–—]\s*(Overview|Parts|Sections).*$", "", title_clean, flags=re.IGNORECASE)
            parts_of_title = title_clean.split()
            if parts_of_title:
                # Last word is usually the appliance type
                appliance_candidates = {"refrigerator", "dishwasher", "washer", "dryer", "oven", "range", "microwave", "freezer"}
                for word in reversed(parts_of_title):
                    if word.lower() in appliance_candidates:
                        appliance_type = word.capitalize()
                        break
                # Everything before the appliance type is the brand
                if appliance_type:
                    idx = title_clean.lower().rfind(appliance_type.lower())
                    brand = title_clean[:idx].strip()
                else:
                    brand = title_clean.strip()

            # ── Section headings (h2, h3) ───────────────────────────────
            sections: list[str] = []
            for tag in soup.find_all(["h2", "h3"]):
                text = tag.get_text(strip=True)
                if text and len(text) < 200:
                    sections.append(text)

            # ── Common symptoms ─────────────────────────────────────────
            common_symptoms: list[str] = []
            # Look for a symptoms section — often a list of links
            symptom_section = soup.find(
                lambda t: t.name in ("h2", "h3") and "symptom" in t.get_text(strip=True).lower()
            )
            if symptom_section:
                # Walk siblings / next section for links or list items
                container = symptom_section.find_next(["ul", "ol", "div"])
                if container:
                    for link in container.find_all("a"):
                        text = link.get_text(strip=True)
                        if text and len(text) < 120:
                            common_symptoms.append(text)
                    if not common_symptoms:
                        for li in container.find_all("li"):
                            text = li.get_text(strip=True)
                            if text and len(text) < 120:
                                common_symptoms.append(text)
            # Also try data attributes or specific class patterns
            if not common_symptoms:
                for link in soup.select('a[href*="Symptoms"]'):
                    text = link.get_text(strip=True)
                    if text and len(text) < 120 and text not in common_symptoms:
                        common_symptoms.append(text)

            # ── Part categories ─────────────────────────────────────────
            part_categories: list[dict] = []
            # Look for category links with counts, e.g., "Ice Maker Parts (12)"
            cat_pattern = re.compile(r"^(.+?)(?:\s*\((\d+)\))?$")
            for link in soup.select('a[href*="/Parts/"]'):
                text = link.get_text(strip=True)
                if not text or len(text) > 100:
                    continue
                m = cat_pattern.match(text)
                if m:
                    cat_name = m.group(1).strip()
                    cat_count = int(m.group(2)) if m.group(2) else None
                    # Filter out generic navigation links
                    if cat_name.lower() in ("parts", "all parts", "view all"):
                        continue
                    if any(c["name"] == cat_name for c in part_categories):
                        continue
                    entry: dict = {"name": cat_name}
                    if cat_count is not None:
                        entry["count"] = cat_count
                    part_categories.append(entry)
                    if len(part_categories) >= 20:
                        break

            return {
                "model_number": mn,
                "model_title": model_title,
                "brand": brand,
                "appliance_type": appliance_type.lower() if appliance_type else "",
                "common_symptoms": common_symptoms[:15],
                "sections": sections[:20],
                "part_categories": part_categories,
                "source_url": url,
            }

    except Exception as exc:
        logger.warning("Error scraping model page %s: %s", url, exc)
        return None


async def _scrape_model_parts(model_number: str, query: str) -> list[dict]:
    """Scrape the PartSelect model parts page and filter by keyword query.

    Returns a list of dicts with part_number, name, price, url.
    """
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    except ImportError:
        logger.warning("crawl4ai not installed — cannot scrape model parts")
        return []

    mn = model_number.strip().upper()
    url = f"https://www.partselect.com/Models/{mn}/Parts/"
    q_lower = query.strip().lower()

    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=60_000,
        magic=True,
    )

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)
            if not result.success:
                logger.warning("Failed to fetch model parts page: %s", url)
                return []

            from bs4 import BeautifulSoup

            soup = BeautifulSoup(result.html, "html.parser")
            parts: list[dict] = []

            # Parts are typically in list items or divs with part links
            # Look for links containing /PS\d+/ pattern (PartSelect part numbers)
            ps_pattern = re.compile(r"(PS\d{6,10})", re.IGNORECASE)

            # Strategy 1: Find part cards/rows with structured data
            for item in soup.select('.mega-m__part, .parts-list__item, [data-part-number]'):
                pn_attr = item.get("data-part-number", "")
                name_el = item.select_one('.mega-m__part__name, .parts-list__name, a')
                price_el = item.select_one('.mega-m__part__price, .price, .js-partPrice')
                link_el = item.select_one('a[href]')

                name = name_el.get_text(strip=True) if name_el else ""
                price = price_el.get_text(strip=True) if price_el else ""
                href = link_el["href"] if link_el else ""

                pn = pn_attr
                if not pn and name:
                    m = ps_pattern.search(name)
                    if m:
                        pn = m.group(1).upper()
                if not pn and href:
                    m = ps_pattern.search(href)
                    if m:
                        pn = m.group(1).upper()

                if pn and name:
                    if q_lower in name.lower():
                        full_url = href if href.startswith("http") else f"https://www.partselect.com{href}" if href else ""
                        parts.append({
                            "part_number": pn.upper(),
                            "name": name,
                            "price": price,
                            "url": full_url,
                        })

            # Strategy 2: Fallback — scan all links for PS numbers
            if not parts:
                seen: set[str] = set()
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    text = link.get_text(strip=True)
                    if not text or len(text) > 200:
                        continue

                    m = ps_pattern.search(href) or ps_pattern.search(text)
                    if not m:
                        continue

                    pn = m.group(1).upper()
                    if pn in seen:
                        continue
                    seen.add(pn)

                    if q_lower in text.lower():
                        full_url = href if href.startswith("http") else f"https://www.partselect.com{href}"
                        parts.append({
                            "part_number": pn,
                            "name": text,
                            "price": "",
                            "url": full_url,
                        })

            return parts[:25]

    except Exception as exc:
        logger.warning("Error scraping model parts %s: %s", url, exc)
        return []


async def _cached_live_compatibility_check(
    part_url: str, part_number: str, model_number: str
) -> Optional[dict]:
    """Deduplicated, cached wrapper around the live browser compatibility check.

    - Returns cached result if the same (part, model) was already checked.
    - Serialises concurrent requests for the same pair so only one browser runs.
    - Evicts oldest entries when the cache exceeds COMPAT_CACHE_MAX.
    """
    pn = part_number.strip().upper()
    mn = model_number.strip().upper()
    cache_key = (pn, mn)

    # Fast path — already cached
    if cache_key in _compat_cache:
        logger.debug("Live compat cache hit: %s / %s", pn, mn)
        return _compat_cache[cache_key]

    # Acquire a per-key lock so concurrent identical requests don't each spawn a browser.
    async with _compat_global_lock:
        if cache_key not in _compat_locks:
            _compat_locks[cache_key] = asyncio.Lock()
        lock = _compat_locks[cache_key]

    async with lock:
        # Double-check after acquiring — another coroutine may have filled it.
        if cache_key in _compat_cache:
            return _compat_cache[cache_key]

        result = await _live_compatibility_check(part_url, model_number)

        # Only cache definitive results (True/False).
        # Inconclusive results (None) may be transient (timeout, page error)
        # and should be retried on the next request.
        if result and result.get("compatible") is not None:
            if len(_compat_cache) >= COMPAT_CACHE_MAX:
                oldest_key = next(iter(_compat_cache))
                del _compat_cache[oldest_key]
                _compat_locks.pop(oldest_key, None)
            _compat_cache[cache_key] = result

        return result


async def _live_compatibility_check(part_url: str, model_number: str) -> Optional[dict]:
    """Use PartSelect's live compatibility widget to check if a model fits.

    Navigates to the part page, fills the model number into the
    "Does this part fit my model?" search box, clicks SEARCH, and reads
    the result + any links from the rendered DOM.

    Returns a dict with 'compatible' (True/False/None) and any relevant URLs
    extracted from the actual page.
    """
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    except ImportError:
        logger.warning("crawl4ai not installed — cannot do live compatibility check")
        return None

    mn = model_number.strip().upper()

    # JS: fill the compat search, click SEARCH, wait for result,
    # then collect all links from the result area into a JSON data attribute.
    js_code = f"""
// Find the compatibility search input
const input = document.querySelector(
  'input.js-compatibilitySearch, input[placeholder*="model number"], .pd__compatibility-tool input[type="text"]'
);
if (!input) {{
  document.title = 'COMPAT_RESULT:ERROR:no_input';
}} else {{
  input.value = '';
  input.focus();
  input.value = '{mn}';
  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
  input.dispatchEvent(new Event('change', {{ bubbles: true }}));

  await new Promise(r => setTimeout(r, 300));
  const btn = document.querySelector(
    'button.js-compatibilitySearchBtn, .pd__compatibility-tool button, .pd__compatibility-tool__search-btn'
  );
  if (btn) btn.click();

  const maxWait = 8000, step = 400;
  let waited = 0;
  let found = false;
  while (waited < maxWait) {{
    const bodyText = document.body.innerText.toLowerCase();

    // Most specific text patterns first — these appear WITH a crossmark,
    // so they must be checked before the generic icon checks.

    // "We couldn't find that part, but we have X parts for that model"
    // MUST check before fuzzy — "couldn't find that part" also contains "couldn't find"
    if (bodyText.includes("couldn't find that part") || bodyText.includes('parts for that model')) {{
      document.title = 'COMPAT_RESULT:NOFIT_HAS_MODEL';
      found = true;
      break;
    }}
    // "Couldn't find an exact match" or "Model was not found" — model number invalid/typo
    if (bodyText.includes("couldn't find an exact match") || bodyText.includes('did find some results') || bodyText.includes('model was not found') || bodyText.includes('please try again')) {{
      document.title = 'COMPAT_RESULT:FUZZY_MODEL';
      found = true;
      break;
    }}
    // "It's a fit!" text
    if (bodyText.includes("it's a fit")) {{
      document.title = 'COMPAT_RESULT:FIT';
      found = true;
      break;
    }}

    // Generic icon checks — only after ruling out the specific text states
    const fit = document.querySelector('.js-Checkmark, .pd__compatibility-tool__checkmark');
    const noFit = document.querySelector('.js-Crossmark, .pd__compatibility-tool__crossmark, .pd__compatibility-tool__no-fit');

    if (fit && fit.offsetParent !== null) {{
      document.title = 'COMPAT_RESULT:FIT';
      found = true;
      break;
    }}
    if (noFit && noFit.offsetParent !== null) {{
      // Crossmark visible — distinguish three cases by the surrounding text:
      // 1. "couldn't find that part" / "parts for that model" → NOFIT_HAS_MODEL (incompatible, model valid)
      // 2. "model was not found" / "couldn't find an exact match" → FUZZY_MODEL (model invalid)
      // 3. Neither → generic NOFIT
      const nearText = (noFit.closest('.pd__compatibility-tool__result, .pd__compatibility-tool') || document.body).innerText.toLowerCase();
      if (nearText.includes("couldn't find that part") || nearText.includes('parts for that model')) {{
        document.title = 'COMPAT_RESULT:NOFIT_HAS_MODEL';
      }} else if (nearText.includes('model was not found') || nearText.includes('please try again') || nearText.includes("couldn't find an exact match") || nearText.includes('did find some results')) {{
        document.title = 'COMPAT_RESULT:FUZZY_MODEL';
      }} else {{
        document.title = 'COMPAT_RESULT:NOFIT';
      }}
      found = true;
      break;
    }}

    await new Promise(r => setTimeout(r, step));
    waited += step;
  }}
  if (!found) {{
    document.title = 'COMPAT_RESULT:FUZZY_MODEL';
  }}

  // Extract all links from the compatibility result area
  const links = {{}};
  const resultArea = document.querySelector(
    '.pd__compatibility-tool__result, .js-compatibilityResult, .pd__compatibility-tool'
  ) || document.body;
  resultArea.querySelectorAll('a[href]').forEach(a => {{
    const text = a.textContent.trim().toLowerCase();
    const href = a.href;
    if (!href || href === '#') return;
    if (text.includes('view model') || text.includes('model detail')) {{
      links['model_details_url'] = href;
    }} else if (text.includes('see results') || text.includes('similar to')) {{
      links['similar_models_url'] = href;
    }} else if (text.includes('finding your model') || text.includes('help finding')) {{
      links['find_model_help_url'] = href;
    }} else if (href.includes('/Models/')) {{
      links['model_details_url'] = links['model_details_url'] || href;
    }} else if (href.includes('nsearchresult') || href.includes('ModelID')) {{
      links['similar_models_url'] = links['similar_models_url'] || href;
    }}
  }});

  // Extract the model description (e.g. "Kenmore Refrigerator") from the match area
  const modelTitle = resultArea.querySelector('.title-md.js-Text, .pd__compatibility-tool__match .js-Text');
  if (modelTitle) {{
    links['model_description'] = modelTitle.textContent.trim();
  }}
  // Extract the "View Model Details" link
  const modelLink = resultArea.querySelector('a.js-Link.js-mnl-modal-link, a.d-block.underline.js-Link');
  if (modelLink && modelLink.href && modelLink.href !== '#') {{
    links['model_details_url'] = links['model_details_url'] || modelLink.href;
  }}

  document.body.setAttribute('data-compat-links', JSON.stringify(links));
}}
"""

    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        page_timeout=60_000,
        magic=True,
        js_code=js_code,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=part_url, config=run_config)
        if not result.success:
            logger.warning("Failed to fetch part page for live compat check: %s", part_url)
            return {"compatible": None}

        from bs4 import BeautifulSoup
        import json as _json

        soup = BeautifulSoup(result.html, "html.parser")
        title = soup.title.string if soup.title else ""

        # Extract links collected by our JS
        links: dict = {}
        body_tag = soup.find("body")
        if body_tag and body_tag.get("data-compat-links"):
            try:
                links = _json.loads(body_tag["data-compat-links"])
            except Exception:
                pass

        if "COMPAT_RESULT:FIT" in title:
            logger.info("Live compat check: %s fits %s", model_number, part_url)
            resp: dict = {"compatible": True}
            if links.get("model_description"):
                resp["model_description"] = links["model_description"]
            if links.get("model_details_url"):
                resp["model_details_url"] = links["model_details_url"]
            return resp

        elif "COMPAT_RESULT:NOFIT_HAS_MODEL" in title:
            logger.info("Live compat check: %s not a fit, but model exists: %s", model_number, part_url)
            resp_nofit: dict = {
                "compatible": False,
                "model_details_url": links.get("model_details_url", ""),
            }
            if links.get("model_description"):
                resp_nofit["model_description"] = links["model_description"]
            return resp_nofit

        elif "COMPAT_RESULT:FUZZY_MODEL" in title:
            logger.info("Live compat check: model %s not found (fuzzy): %s", model_number, part_url)
            return {
                "compatible": None,
                "model_not_found": True,
                "similar_models_url": links.get("similar_models_url", ""),
                "find_model_help_url": links.get("find_model_help_url", ""),
            }

        elif "COMPAT_RESULT:NOFIT" in title:
            logger.info("Live compat check: %s does NOT fit %s", model_number, part_url)
            return {"compatible": False}

        else:
            logger.warning("Live compat check inconclusive (title=%s): %s / %s", title, part_url, model_number)
            return {"compatible": None}

