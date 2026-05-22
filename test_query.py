import asyncio
import logging

logging.basicConfig(level=logging.INFO)

from server import search_products
from worker import start_background_worker

async def main():
    worker_task = asyncio.create_task(start_background_worker())
    await asyncio.sleep(0.5)

    try:
        print("\n=== QUERY 1: First call (triggers Layer 3 — miss + background build) ===\n")
        result1 = await search_products("python coding books", "books.toscrape.com")
        print(f"Result 1:\n{result1}\n")

        print("=== Waiting 120s for background worker to generate scraper... ===\n")
        await asyncio.sleep(120)

        print("=== QUERY 2: Second call (should hit Layer 2 — generated scraper) ===\n")
        result2 = await search_products("python coding books", "books.toscrape.com")
        print(f"Result 2:\n{result2}\n")
    except Exception as e:
        print(f"Background worker failed with: {e}")
        raise
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


asyncio.run(main())
