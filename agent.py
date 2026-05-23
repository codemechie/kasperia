import asyncio
import json
import os
import re

from openai import OpenAI
from server import search_products

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-r1:8b")

client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key=OLLAMA_API_KEY,
)
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Searches a specific e-commerce store for products and extracts metadata (prices, ratings)",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Product to search for (e.g. 'running shoes')"},
                    "domain": {"type": "string", "description": "Store domain to search (e.g. 'nike.com', 'amazon.com')"}
                },
                "required": ["query", "domain"]
            }
        }
    }
]
#Ask the model a question
user_prompt = "Show me best running shoes from nike"
print(f"User prompt: {user_prompt}\n")

response = client.chat.completions.create(
    model=LLM_MODEL,
    messages=[{"role": "user", "content": user_prompt}],  # type: ignore[arg-type]
    tools=tools, # type: ignore[arg-type]
    tool_choice="auto"
)

def _parse_tool_call(content: str) -> dict | None:
    match = re.search(r'\{.*"name"\s*:\s*"search_products".*"arguments"\s*:\s*(\{.*\})\s*\}', content, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    return None

response_message = response.choices[0].message
tool_calls = response.choices[0].message.tool_calls

args = None
if tool_calls:
    for tool_call in tool_calls:
        if tool_call.function.name == "search_products":
            args = json.loads(tool_call.function.arguments)
            break

if args is None and response_message.content:
    args = _parse_tool_call(response_message.content)

if args:
    print(f"LLM decided to call tool with args: {args}")

    query = args.get("query")
    domain = args.get("domain")

    if not query or not domain:
        print(f"Error: Missing required parameters. query={query}, domain={domain}")
        exit(1)
    raw_web_data = asyncio.run(search_products(query=query, domain=domain))
    print(f"Final product data: \n{raw_web_data}")
else:
    print(f"Response message: {response_message.content}")