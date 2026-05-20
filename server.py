import json
import os

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from mcp.server.fastmcp import FastMCP

from dotenv import load_dotenv
load_dotenv()

mcp = FastMCP("ProductSearchServer")

#Use a standard, clean user-agent to prevent targets from instantly dropping queries
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36)"
}

def extract_schema_data(url: str) -> dict | None:
    #Fetches a URL and extracts standard schema.org product metadata.
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")
        scripts = soup.find_all("script", type="application/ld+json")

        for script in scripts:
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get("@type") == "Product":
                        return data
                    if "@graph" in data:
                        for item in data["@graph"]:
                            if item.get("@type") == "Product":
                                return item
            except (json.JSONDecodeError, TypeError):
                continue
    except Exception:
        return None
    return None

@mcp.tool()
def search_products_mock(prompt: str, brands: list[str], min_price: float, max_price: float) -> str:
    mock_web_data = [
        {
            "raw_title": "Nike Air Zoom Pegasus 40",
            "raw_brand": "Nike",
            "raw_price": 4999,
            "currency": "INR",
            "rating": 4.5,
            "reviews": 2341,
            "url": "https://www.nike.com/air-zoom-pegasus-40",
        },
        {
            "raw_title": "Adidas Ultraboost Light",
            "raw_brand": "Adidas",
            "raw_price": 5499,
            "currency": "INR",
            "rating": 4.6,
            "reviews": 1876,
            "url": "https://www.adidas.com/ultraboost-light",
        },
        {
            "raw_title": "Puma Velocity Nitro 2",
            "raw_brand": "Puma",
            "raw_price": 3999,
            "currency": "INR",
            "rating": 4.3,
            "reviews": 1123,
            "url": "https://www.puma.com/velocity-nitro-2",
        },
        {
            "raw_title": "Nike Revolution 6",
            "raw_brand": "Nike",
            "raw_price": 3299,
            "currency": "INR",
            "rating": 4.2,
            "reviews": 4567,
            "url": "https://www.nike.com/revolution-6",
        },
        {
            "raw_title": "Adidas Adizero Boston 12",
            "raw_brand": "Adidas",
            "raw_price": 5999,
            "currency": "INR",
            "rating": 4.7,
            "reviews": 892,
            "url": "https://www.adidas.com/adizero-boston-12",
        },
    ]
    return json.dumps(mock_web_data)


@mcp.tool()
def search_products(prompt: str, brands: list[str], min_price: float, max_price: float) -> str:
    """Searches DuckDuckGo for products using zero-cost API requests
        and applies micro-parsing via BeautifulSoup to extract e-commerce metadata
    """
    if not brands:
        return json.dumps({"error": "No brands provided"})

    if min_price < 0 or max_price < 0 or min_price > max_price:
        return json.dumps({"error": "Invalid price range"})

    brand_query = " OR ".join(brands)
    search_query = f"{prompt} ({brand_query}) price {min_price} to {max_price}"
    compiled_products = []

    try:
        print(f"Querying DuckDuckGo for: {search_query}")
        with DDGS() as ddgs:
            search_results = list(ddgs.text(search_query, max_results=5))

        for result in search_results:
            target_url = result.get("href") or result.get("url")
            if not target_url:
                continue
            print(f"Parsing target page: {target_url}")

            product_schema = extract_schema_data(target_url)
            if product_schema:
                offers = product_schema.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                price = offers.get("price") if isinstance(offers, dict) else None
                currency = offers.get("priceCurrency") if isinstance(offers, dict) else "INR"

                agg_rating = product_schema.get("aggregateRating", {})
                rating_val = agg_rating.get("ratingValue") if isinstance(agg_rating, dict) else None
                review_count = agg_rating.get("reviewCount") if isinstance(agg_rating, dict) else None

                brand_raw = product_schema.get("brand")
                brand_name = brand_raw.get("name") if isinstance(brand_raw, dict) else brand_raw

                compiled_products.append({
                    "raw_title": product_schema.get("name"),
                    "raw_brand": brand_name,
                    "raw_price": price,
                    "currency": currency,
                    "rating": rating_val,
                    "reviews": review_count,
                    "url": target_url,
                })
            else:
                compiled_products.append({
                    "raw_title": result.get("title"),
                    "raw_snippet": result.get("body"),
                    "url": target_url,
                })

        return json.dumps(compiled_products)
    except Exception as e:
        return json.dumps({"error": f"Search/extraction failed: {str(e)}"})

if __name__ == "__main__":
    mcp.run()