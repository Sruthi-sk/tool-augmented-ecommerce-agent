"""PartSelect website retrieval and HTML parsing."""
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.partselect.com"


@dataclass
class PartData:
    part_number: str
    name: str
    price: str
    in_stock: bool
    description: str
    source_url: str
    manufacturer_part_number: Optional[str] = None
    compatible_models: list[str] = field(default_factory=list)
    installation_steps: list[str] = field(default_factory=list)
    symptoms: list[str] = field(default_factory=list)


@dataclass
class PartSummary:
    part_number: str
    name: str
    price: str
    url: str


class PartSelectRetriever:
    def __init__(self):
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; PartSelectAgent/1.0)"
            },
            timeout=15.0,
            follow_redirects=True,
        )

    async def close(self):
        await self._client.aclose()

    def parse_part_page(self, html: str, source_url: str) -> PartData:
        """Parse a part detail page into structured PartData."""
        soup = BeautifulSoup(html, "html.parser")

        name = ""
        title_el = soup.select_one("h1.title-lg") or soup.select_one("h1")
        if title_el:
            name = title_el.get_text(strip=True)

        price = ""
        price_el = soup.select_one(".price") or soup.select_one("[itemprop='price']")
        if price_el:
            price = price_el.get_text(strip=True)

        in_stock = False
        avail_el = soup.select_one(".pd__availability")
        if avail_el and "In Stock" in avail_el.get_text():
            in_stock = True

        description = ""
        desc_el = soup.select_one(".pd__description")
        if desc_el:
            description = desc_el.get_text(strip=True)

        part_number = ""
        pn_el = soup.select_one(".pd__part-number")
        if pn_el:
            spans = pn_el.select("span")
            if len(spans) >= 2:
                part_number = spans[-1].get_text(strip=True)

        mfr_number = None
        mfr_el = soup.select_one(".pd__mfr-number")
        if mfr_el:
            spans = mfr_el.select("span")
            if len(spans) >= 2:
                mfr_number = spans[-1].get_text(strip=True)

        return PartData(
            part_number=part_number,
            name=name,
            price=price,
            in_stock=in_stock,
            description=description,
            source_url=source_url,
            manufacturer_part_number=mfr_number,
        )

    def parse_search_results(self, html: str) -> list[PartSummary]:
        """Parse a search results page into PartSummary list."""
        soup = BeautifulSoup(html, "html.parser")
        results = []

        for item in soup.select(".mega-m__part"):
            name_el = item.select_one(".mega-m__part__name")
            price_el = item.select_one(".mega-m__part__price")
            pn_el = item.select_one(".mega-m__part__number")

            if name_el and pn_el:
                results.append(
                    PartSummary(
                        part_number=pn_el.get_text(strip=True),
                        name=name_el.get_text(strip=True),
                        price=price_el.get_text(strip=True) if price_el else "",
                        url=name_el.get("href", ""),
                    )
                )

        return results

    async def fetch_part(self, part_number: str) -> Optional[PartData]:
        """Fetch and parse a part detail page from PartSelect."""
        url = f"{BASE_URL}/PS{part_number}.htm" if not part_number.startswith("PS") else f"{BASE_URL}/{part_number}.htm"
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            return self.parse_part_page(resp.text, str(resp.url))
        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch part {part_number}: {e}")
            return None

    async def search(self, query: str, appliance_type: str = "") -> list[PartSummary]:
        """Search PartSelect for parts matching a query."""
        search_url = f"{BASE_URL}/Search.aspx"
        params = {"q": query}
        if appliance_type:
            params["appliance"] = appliance_type
        try:
            resp = await self._client.get(search_url, params=params)
            resp.raise_for_status()
            return self.parse_search_results(resp.text)
        except httpx.HTTPError as e:
            logger.warning(f"Search failed for '{query}': {e}")
            return []

    async def fetch_model_parts(self, model_number: str) -> list[PartSummary]:
        """Fetch parts for a specific model number."""
        url = f"{BASE_URL}/Models/{model_number}/Parts/"
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            return self.parse_search_results(resp.text)
        except httpx.HTTPError as e:
            logger.warning(f"Model parts fetch failed for {model_number}: {e}")
            return []
