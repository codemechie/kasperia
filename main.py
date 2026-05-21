import asyncio
import logging
import sys
from server import mcp

#Setup entrypoint logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("KasperiaRuntime")

def main():
    """Main entry point of the application
    Launches MCP server, which automatically
    triggers the background worker.
    """
    logger.info("Starting Kasperia Engine")
    logger.info("Starting MCP Server")
    try:
        mcp.run()
        logger.info("Kasperia Engine stopped successfully. Goodbye!")
    except KeyboardInterrupt:
        logger.info("Shutdown signal received (Ctrl+C)")
    except Exception:
        logger.exception("Unexpected error while running MCP server")
        raise
    finally:
        logger.info("Kasperia Engine stopped.")
if __name__ == "__main__":
    main()