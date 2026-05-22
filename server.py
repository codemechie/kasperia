import asyncio
import json
import logging
from contextlib import asynccontextmanager

import httpx
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

from scrapers import get_scraper, all_scrapers
from state import state
from worker import start_background_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KasperiaServer")

@asynccontextmanager
async def app_lifespan(server: FastMCP):
    worker_task = asyncio.create_task(start_background_worker(), name="background-worker")
    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


mcp = FastMCP("Kasperia Deal Agent", lifespan=app_lifespan)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36)"
}


async def extract_product_data(query: str, domain: str) -> dict | None:
    logger.info(f"Running generic fallback parser on {domain} for {query}")
    try:
        # Normalize domain: strip protocol and path
        clean_domain = domain.replace("https://", "").replace("http://", "").split("/")[0].strip()

        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://{clean_domain}", headers=HEADERS, timeout=5.0)
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
async def search_products(query: str, domain: str) -> dict:
    """Searches items on a specific store domain
        Returns instant data via static scraper
        real-time scraper generation in the background
    """
    domain_clean = domain.lower().strip()
    cache_key = f"{domain_clean}:{query.lower().strip()}"

    #Layer 1: Check system memory cache
    if cache_key in state.cache:
        logger.info(f"Using cached scraper from {cache_key}")
        return {
            "status": "success",
            "source": "cache",
            "data": state.cache[cache_key]
        }
    # Layer 2: Match Static Scraper
    if domain_clean in state.scraper_registry:
        logger.info(f"Found dedicated scraper for {domain_clean}")
        scraper = state.scraper_registry[domain_clean]

        try:
            raw_data = await scraper.scrape_products(query)
            state.cache[cache_key] = raw_data
            return {
                "status": "success",
                "source": "static_scraper",
                "data": raw_data
            }
        except Exception as e:
            logger.error(f"Static scraper failed for {domain_clean}: {str(e)}")
    #Layer 3: Miss, Dispatch Dynamic Agent Worker and Run Fallback Parser Concurrently
    logger.info(f"No static scraper found for {domain_clean}. Dispatching background build task...")
    #Instaneous, non-blocking push to the shared container
    await state.queue.put({"domain": domain_clean, "query": query})

    #Instantly trigger the fallback parser
    fallback_data = await extract_product_data(query, domain_clean)

    if fallback_data is not None:
        return {
            "status": "success",
            "source": "fallback_parser",
            "data": fallback_data,
            "message": f"Returning initial results. A custom parser for {domain_clean} is being generated by our agent in the background.",
        }

    return {
        "status": "pending",
        "source": "fallback_parser",
        "data": None,
        "message": f"I've pulled some immediate deals using my fallback scanner but I noticed I don't have an optimized tracker for {domain_clean} yet. I am building a custom scraper for this site in the background so your future searches here will be much faster and more accurate.",
        "pending": True,
    }

if __name__ == "__main__":
    mcp.run()
