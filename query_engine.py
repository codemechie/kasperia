import asyncio
from fastmcp.client import Client, SSETransport

async def main():
    transport = SSETransport(url="http://100.113.197.26:8000/sse")
    async with Client(transport) as client:
        result = await client.call_tool("search_products", {"query": "mechanical keyboard", "domain": "newegg.com"})
        for c in result.content:
            if c.type == "text":
                print(c.text)

asyncio.run(main())
