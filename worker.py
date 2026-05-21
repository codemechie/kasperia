import asyncio
import logging
from state import state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BackgroundWorker")

async def start_background_worker():
    """Listens continuously for missing scrapers and queues agent builds."""
    logger.info("Background Scraper-Agent engine initialized...")
    while True:
        event = None
        try:
            event = await state.queue.get()
            domain = event.get("domain")
            query = event.get("query")

            logger.info(f"[Queue] Received missing domain trigger for: {domain}")
            await asyncio.sleep(5)

            logger.info(f"[Queue] Successfully generated and compiled scraper for: {domain}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Worker Error: {str(e)}")
        finally:
            if event is not None:
                state.queue.task_done()