import json
from openai import OpenAI
from server import search_products
#Connect to Ollama (default port 1143)
client = OpenAI(
    base_url="http://127.0.0.1:11435/v1",
    api_key="ollama"
)
#1. Define the tool schema so Mistral knows it exists
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Searches the web for the products based on brand and price constraints",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The type of product"},
                    "brands": {"type": "array", "items": {"type": "string"}, "description": "The brand names"},
                    "min_price": {"type": "float"},
                    "max_price": {"type": "float"}
                },
                "required": ["prompt", "brands", "min_price", "max_price"]
            }
        }
    }
]
#Ask the model a question
user_prompt = "Show me running shoes in the range of INR 3000-6000. Show top deals from nike and adidas and other top brands as well."
print(f"User prompt: {user_prompt}\n")

response = client.chat.completions.create(
    model="qwen2.5:7b",
    messages=[{"role": "user", "content": user_prompt}],  # type: ignore[arg-type]
    tools=tools, # type: ignore[arg-type]
    tool_choice="auto"
)

#Check if Qwen decided to call your MCP tool
response_message = response.choices[0].message
tool_calls = response.choices[0].message.tool_calls

if tool_calls:
    for tool_call in tool_calls:
        if tool_call.function.name == "search_products":
            args = json.loads(tool_call.function.arguments)
            print(f"Qwen decided to call tool with args: {args}")

            raw_web_data = search_products(
                prompt=args.get("prompt"),
                brands=args.get("brands"),
                min_price=args.get("min_price"),
                max_price=args.get("max_price")
            )
            print(f"Final product data: \n{raw_web_data}")
else:
    print(f"Response message: {response_message.content}")