import json

import requests
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

from scrapers import get_scraper, all_scrapers

mcp = FastMCP("ProductSearchServer")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36)"
}

USD_TO_INR = 83


def extract_product_data(url: str) -> dict | None:
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")

        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if item.get("@type") == "Product":
                        return item
                    if "@graph" in item:
                        for g in item["@graph"]:
                            if g.get("@type") == "Product":
                                return g
            except (json.JSONDecodeError, TypeError):
                continue

        title = (
            soup.find("meta", property="og:title")
            or soup.find("meta", attrs={"name": "twitter:title"})
            or soup.find("title")
        )
        description = (
            soup.find("meta", property="og:description")
            or soup.find("meta", attrs={"name": "description"})
        )
        price = soup.find("meta", property="product:price:amount")
        currency = soup.find("meta", property="product:price:currency")

        if title:
            return {
                "name": title.get("content") or title.get_text(strip=True) if hasattr(title, "get_text") else title.get("content"),
                "description": description.get("content") if description else None,
                "offers": {
                    "price": price.get("content") if price else None,
                    "priceCurrency": currency.get("content") if currency else None,
                },
                "brand": {"name": None},
                "aggregateRating": None,
            }
    except Exception:
        return None
    return None


@mcp.tool()
def search_products(prompt: str, brands: list[str] | None = None, min_price: float | None = None, max_price: float | None = None) -> str:
    """Scrapes brand sites directly for product deals and extracts e-commerce metadata"""
    compiled_products = []
    seen = set()

    targets = [(b, get_scraper(b)) for b in (brands or [])]
    if not any(s for _, s in targets):
        targets = list(all_scrapers())

    for brand_name, scraper in targets:
        if not scraper:
            continue
        try:
            raw = scraper.search(prompt)
        except Exception as e:
            print(f"{brand_name} scraper failed: {e}")
            continue

        for p in raw:
            url = p.get("url")
            if not url or url in seen:
                continue
            seen.add(url)

            price = p.get("price")
            currency = p.get("currency", "USD")
            price_inr = None
            if price is not None:
                if currency == "USD":
                    price_inr = price * USD_TO_INR
                elif currency == "INR":
                    price_inr = price
                else:
                    price_inr = price * USD_TO_INR

            if price_inr is not None:
                if min_price is not None and price_inr < min_price:
                    continue
                if max_price is not None and price_inr > max_price:
                    continue

            price_factor = max(0.1, (6000 - (price_inr or 6000)) / 3000)
            vfm = round(price_factor * 5, 1)

            compiled_products.append({
                "vendor": p.get("vendor", brand_name.title()),
                "make": p.get("make", "Unknown"),
                "price": round(price_inr) if price_inr else None,
                "vfm": vfm,
                "rating": None,
                "reviews_count": None,
                "url": url,
            })

    return json.dumps(compiled_products)


if __name__ == "__main__":
    mcp.run()
