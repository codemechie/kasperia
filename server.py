import json

import requests
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ProductSearchServer")

#Use a standard, clean user-agent to prevent targets from instantly dropping queries
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36)"
}

def extract_product_data(url: str) -> dict | None:
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")

        # Try schema.org JSON-LD first
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

        # Fallback: extract from Open Graph and meta tags
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
def search_products(prompt: str, brands: list[str], min_price: float, max_price: float) -> str:
    """Searches DuckDuckGo for products and parses target pages
        to extract e-commerce metadata
    """
    if not brands:
        return json.dumps({"error": "No brands provided"})

    if min_price < 0 or max_price < 0 or min_price > max_price:
        return json.dumps({"error": "Invalid price range"})

    DDG_URL = "https://html.duckduckgo.com/html/"
    compiled_products = []

    try:
        for brand in brands:
            search_query = f"{prompt} {brand}"
            response = requests.post(DDG_URL, data={"q": search_query}, headers=HEADERS, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "lxml")
            links = soup.find_all("a", class_="result__a")
            print(f"DDG returned {len(links)} results for {brand}")

            for link in links[:3]:
                target_url = link.get("href")
                if not target_url or target_url.startswith("https://duckduckgo.com/y.js"):
                    continue
                if any(p["url"] == target_url for p in compiled_products):
                    continue
                print(f"Parsing: {target_url}")

                product_schema = extract_product_data(target_url)
                if product_schema:
                    offers = product_schema.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    price = offers.get("price") if isinstance(offers, dict) else None
                    currency = offers.get("priceCurrency") if isinstance(offers, dict) else "INR"

                    agg_rating = product_schema.get("aggregateRating", {})
                    rating_val = agg_rating.get("ratingValue") if isinstance(agg_rating, dict) else 0.0
                    review_count = agg_rating.get("reviewCount") if isinstance(agg_rating, dict) else 0.0

                    brand_raw = product_schema.get("brand")
                    brand_name = brand_raw.get("name", "Unknown") if isinstance(brand_raw, dict) else brand_raw or "Unknown"

                    try:
                        price_float = float(price) if price else 6000
                        price_factor = max(0.1, (6000 - price_float) / 3000)
                        rating_float = float(rating_val) if rating_val else 0
                        vfm_score = round((rating_float + (price_factor * 5)) / 2, 1)
                    except (ValueError, TypeError):
                        vfm_score = 5.0

                    compiled_products.append({
                        "vendor": brand_name,
                        "make": product_schema.get("name", "Unknown Model"),
                        "price": int(float(price)) if price else 0,
                        "vfm": vfm_score,
                        "rating": rating_val if rating_val > 0 else None,
                        "reviews_count": review_count,
                        "url": target_url,
                    })
                else:
                    compiled_products.append({
                        "vendor": brand if any(b.lower() in target_url.lower() for b in brands) else None,
                        "make": link.get_text(strip=True),
                        "price": None,
                        "vfm": None,
                        "rating": None,
                        "reviews_count": None,
                        "url": target_url,
                    })

        return json.dumps(compiled_products)
    except Exception as e:
        return json.dumps({"error": f"Search/extraction failed: {str(e)}"})

if __name__ == "__main__":
    mcp.run()