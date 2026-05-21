import json
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

class AdidasScraper:
    def search(self, query: str) -> list[dict]:
        url = f"https://www.adidas.com/us/search?q={requests.utils.quote(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.content, "lxml")

        products = []
        search_data = self._find_embedded_json(soup)
        if search_data:
            products = self._parse_products(search_data)

        return products

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
            if isinstance(item, dict):
                product = None
                if "item" in item:
                    product = item["item"]
                elif "product" in item:
                    product = item["product"]
                else:
                    product = item

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
