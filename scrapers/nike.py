import json
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def _resolve_url(pdp_url):
    if isinstance(pdp_url, dict):
        return pdp_url.get("url") or pdp_url.get("path", "")
    if isinstance(pdp_url, str):
        return pdp_url
    return ""


class NikeScraper:
    def search(self, query: str) -> list[dict]:
        url = f"https://www.nike.com/w?q={requests.utils.quote(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "lxml")

        products = {}
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                wall = data.get("props", {}).get("pageProps", {}).get("initialState", {}).get("Wall", {})
                for grouping in wall.get("productGroupings", []):
                    for p in grouping.get("products", []):
                        key = p.get("groupKey")
                        if not key:
                            continue

                        copy = p.get("copy", {})
                        prices = p.get("prices", {})
                        pdp = _resolve_url(p.get("pdpUrl", ""))
                        full_url = f"https://www.nike.com{pdp}" if pdp and pdp.startswith("/") else pdp

                        current = products.get(key)
                        existing_price = current["price"] if current else None
                        new_price = prices.get("currentPrice")
                        if current and existing_price is not None and new_price is not None and existing_price <= new_price:
                            continue

                        products[key] = {
                            "vendor": "Nike",
                            "make": f"{copy.get('title', '')} - {copy.get('subTitle', '')}".strip(" -"),
                            "price": new_price,
                            "currency": prices.get("currency", "USD"),
                            "rating": None,
                            "reviews_count": None,
                            "url": full_url or None,
                        }
            except (KeyError, TypeError, json.JSONDecodeError):
                pass

        if not products:
            return self._parse_html(soup)

        return list(products.values())

    def _parse_html(self, soup: BeautifulSoup) -> list[dict]:
        seen = set()
        products = []
        for card in soup.select("[class*=product-card]"):
            link = card.select_one("[class*=product-card__link-overlay]")
            img = card.select_one("[class*=product-card__hero-image]")
            name = link.get_text(strip=True) if link else None
            url = link.get("href") if link else None
            if not name:
                alt = img.get("alt") if img else None
                if alt:
                    name = alt
            if name and url not in seen:
                seen.add(url or name)
                products.append({
                    "vendor": "Nike",
                    "make": name,
                    "price": None,
                    "currency": "USD",
                    "rating": None,
                    "reviews_count": None,
                    "url": url,
                })
        return products
