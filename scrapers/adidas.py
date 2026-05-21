import json
import httpx
from urllib.parse import quote
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from scrapers.base import BaseScraper


class AdidasScraper(BaseScraper):
    @property
    def target_domain(self) -> str:
        return "adidas.com"

    async def scrape_products(self, query: str) -> List[Dict[str, Any]]:
        url = f"https://www.adidas.com/us/search?q={quote(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            try:
                response = await client.get(url)
                if response.status_code != 200:
                    return []
                soup = BeautifulSoup(response.text, "lxml")
            except Exception:
                return []

        search_data = self._find_embedded_json(soup)
        if not search_data:
            return []

        return self._parse_products(search_data)

    def _find_embedded_json(self, soup: BeautifulSoup) -> dict | None:
        for script in soup.find_all("script"):
            if not script.string:
                continue
            text = script.string.strip()
            if not text.startswith("{"):
                continue
            try:
                data = json.loads(text)
                if self._is_product_data(data):
                    return data
            except json.JSONDecodeError:
                continue
        return None

    def _is_product_data(self, data: dict) -> bool:
        raw = data.get("raw") or data.get("searchResult") or data
        if isinstance(raw, dict):
            items = raw.get("itemListElement") or raw.get("items") or raw.get("products")
            if items and isinstance(items, list):
                return True
        if "itemListElement" in str(data.keys()):
            return True
        return False

    def _parse_products(self, data: dict) -> list[dict]:
        products = []
        raw = data.get("raw") or data.get("searchResult") or data
        items = (raw.get("itemListElement") if isinstance(raw, dict) else None) or \
                (raw.get("items") if isinstance(raw, dict) else None) or \
                (raw.get("products") if isinstance(raw, dict) else None) or []

        for item in items:
            if not isinstance(item, dict):
                continue

            product = item.get("item") or item.get("product") or item
            if not isinstance(product, dict):
                continue

            name = product.get("name")
            offers = product.get("offers", {}) if isinstance(product.get("offers"), dict) else {}
            price = offers.get("price")
            currency = offers.get("priceCurrency", "USD")
            url = product.get("@id") or product.get("url")

            products.append({
                "vendor": "Adidas",
                "make": name or "Unknown",
                "price": float(price) if price else None,
                "currency": currency,
                "rating": None,
                "reviews_count": None,
                "url": url,
            })

        return products
