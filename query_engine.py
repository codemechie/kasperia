import asyncio
import logging

logging.basicConfig(level=logging.INFO)

from fastmcp.client import Client, SSETransport

async def main():
    url = "http://100.113.197.26:8000/sse"
    transport = SSETransport(url=url)
    async with Client(transport) as client:
        result = await client.call_tool("search_products", {"query": "mechanical keyboard", "domain": "newegg.com"})
        for content in result.content:
            if content.type == "text":
                print(content.text)

if __name__ == "__main__":
    asyncio.run(main())
