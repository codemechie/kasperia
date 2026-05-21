# Kasperia 🛍️

> An intelligent AI agent that searches e-commerce websites in real time to find you the best deals across multiple vendors—all powered by local LLMs and zero external APIs.

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![FastMCP](https://img.shields.io/badge/FastMCP-Server-green.svg)](https://github.com/jlouis/fastmcp)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-orange.svg)](https://ollama.ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🚀 What is Kasperia?

Kasperia is a **self-healing e-commerce search agent** that:

- 🤖 **Understands natural language** queries to determine which stores to search
- 🔍 **Auto-generates store-specific scrapers** on demand using LLM code generation
- ⚡ **Returns instant results** via fallback parsing while learning new sites
- 🔒 **Runs locally** with Ollama (Qwen 2.5)—no cloud APIs, no API keys
- 🛡️ **Isolates generated code** in sandboxed execution environments for safety

Ask Kasperia: *"Find me running shoes under $100 on Nike and Amazon"*, and it will:
1. Route your query to the relevant stores
2. Fetch current product data (generating custom scrapers if needed)
3. Return ranked deals with real prices and links

---

## 🏗️ Architecture Overview

### Three-Layer Lookup Pipeline

```
User Query
    ↓
┌─────────────────────────────────────────────────────┐
│ Layer 1: Cache (instant hit)                        │
│ ✓ In-memory registry of known scrapers              │
│ → Returns cached results immediately                │
└─────────────────────────────────────────────────────┘
    ↓ (miss)
┌─────────────────────────────────────────────────────┐
│ Layer 2: Static Scraper (registered handler)        │
│ ✓ Deployed BaseScraper subclass for domain          │
│ → Executes known scraper, returns results           │
└─────────────────────────────────────────────────────┘
    ↓ (miss)
┌─────────────────────────────────────────────────────┐
│ Layer 3: Fallback + Background Build                │
│ ✓ Generic JSON-LD/OG meta parser                    │
│ → Returns initial results immediately               │
│ ↓ (async)                                           │
│ Worker generates site-specific scraper via LLM      │
│ Validates & deploys to Layer 2 for future queries   │
└─────────────────────────────────────────────────────┘
```

### Dual-Agent System

| Component | Role | Responsibility |
|-----------|------|-----------------|
| **Orchestrator** (`agent.py`) | User-facing LLM | Analyzes queries, routes to appropriate stores, invokes `search_products()` |
| **Code-Gen Worker** (`worker.py`) | Background LLM | Reverse-engineers store DOM → generates Python scraper class |

### Worker Pipeline (Self-Healing)

```
1. fetch_target_dom_sample()
   └─ Lightweight HTTP GET, extract ~5k chars

2. run_llm_codegen_agent()
   └─ Send DOM to Ollama, receive Python Scraper class

3. load_agent_scraper()
   └─ Compile in isolated module scope
   └─ Validate Scraper class exists
   └─ Instantiate & bind to state.scraper_registry

4. Future queries use Layer 2 (instant execution)
```

---

## ⚡ Key Features

### Self-Healing Scrapers
When an e-commerce site isn't yet supported, Kasperia automatically generates a custom scraper via LLM code generation—no manual configuration required.

### Instant Fallback
Even while a dedicated scraper is being built in the background, users get immediate results from generic metadata parsing (JSON-LD, Open Graph).

### Isolated Code Execution
LLM-generated Python code runs in a sandboxed module scope, preventing corrupted or malicious code from affecting the core system.

### Zero External Dependencies
- ✓ No cloud APIs
- ✓ No subscription costs
- ✓ No API keys
- ✓ Pure HTTP + BeautifulSoup + local Ollama

### Clean Separation of Concerns
One LLM handles user intent and routing; another specializes in code generation. Each focuses on what it does best.

---

## 📁 Project Structure

```
kasperia/
├── main.py                  # Entrypoint, graceful lifecycle & lifespan hooks
├── server.py                # FastMCP server, search_products tool, fallback parser
├── agent.py                 # Orchestrator LLM client (user-facing)
├── worker.py                # Background worker (DOM fetch → code-gen → validate → deploy)
���── state.py                 # In-memory AppState (scraper_registry, cache, queue, locks)
├── scrapers/
│   ├── base.py              # BaseScraper abstract base class
│   ├── evaluator.py         # Isolated code compiler & validator (sandboxed execution)
│   ├── schema.py            # Pydantic ProductDeal model
│   ├── nike.py              # Nike scraper (legacy)
│   ├── adidas.py            # Adidas scraper (legacy)
│   └── __init__.py          # Legacy SCRAPERS registry
└── README.md                # This file
```

---

## 🔧 Getting Started

### Prerequisites

- **Python 3.12+**
- **Ollama** running locally with Qwen 2.5 model
  ```bash
  ollama pull qwen:2.5
  ollama serve
  ```

### Installation

```bash
git clone https://github.com/codemechie/kasperia.git
cd kasperia
pip install -r requirements.txt
```

### Running Kasperia

```bash
python main.py
```

The FastMCP server starts on a local port (default: see logs). The background worker thread initializes automatically via the lifespan hook.

### Example Query

```python
# Via MCP client or HTTP POST to the server:
{
  "tool": "search_products",
  "input": {
    "query": "waterproof hiking boots",
    "domain": "amazon.com"
  }
}
```

Response:
```json
{
  "results": [
    {
      "product_name": "Merrell Moab 2 Waterproof",
      "price": "$89.99",
      "url": "https://amazon.com/...",
      "store": "amazon.com"
    },
    ...
  ]
}
```

---

## 📊 How It Works (Flow Diagram)

```
┌──────────────────┐
│   User Query     │
│ (Natural Lang)   │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────┐
│  Orchestrator Agent (Qwen)       │
│  • Parse intent                  │
│  • Identify store(s)             │
│  • Call search_products()        │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│  Server Layer Lookup             │
├──────────────────────────────────┤
│  L1: Cache Hit? → Return          │
���  L2: Static Scraper? → Execute    │
│  L3: Fallback + Queue Build       │
└────────┬─────────────────────────┘
         │
         ├─────────────────┬────────────────────┐
         │                 │                    │
    ┌────▼───┐      ┌─────▼──────┐      ┌──────▼──────┐
    │ Results│      │  Async Job │      │   Future    │
    │ (Fast) │      │  in Queue  │      │  Layer-2    │
    │        │      │            │      │  Registry   │
    └────┬───┘      └─────┬──────┘      └─────────────┘
         │                │
         │                ▼
         │          ┌────────────────────────┐
         │          │  Code-Gen Worker       │
         │          │ (Background Qwen)      │
         │          ├────────────────────────┤
         │          │ 1. Fetch DOM sample    │
         │          │ 2. LLM → Python class  │
         │          │ 3. Validate & Sandbox  │
         │          │ 4. Deploy to Layer 2   │
         │          └────────────────────────┘
         │
         └──────────────────┬───────────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │ Best Deals ✓ │
                    └──────────────┘
```

---

## 🔐 Safety & Reliability

- **Sandboxed Code Execution**: LLM-generated scrapers run in isolated module scopes, preventing system corruption
- **Validation Layer**: All generated code is parsed, inspected, and validated before execution
- **Graceful Fallbacks**: If scraper generation fails, users still get results from generic metadata parsing
- **Async Worker Queue**: Background tasks don't block user responses

---

## 📝 State Management

Kasperia uses an in-memory `AppState` container (`state.py`) to manage:

- `scraper_registry`: Active, validated scraper classes
- `cache`: Query results cache
- `queue`: Async job queue for scraper generation
- `locks`: Thread-safe access patterns

---

## 🤝 Contributing

Contributions are welcome! Areas for enhancement:

- Additional static scrapers for popular stores
- Improved DOM parsing strategies
- LLM prompt engineering for better code generation
- Caching strategies (Redis, SQLite)
- Web UI for query submission

---

## 📄 License

MIT License — See [LICENSE](LICENSE) for details.

---

## 🎯 Roadmap

- [ ] Multi-model support (expand beyond Qwen 2.5)
- [ ] Persistent scraper storage
- [ ] Price history tracking & deal alerts
- [ ] Web dashboard
- [ ] Docker containerization
- [ ] Advanced filtering (brand, rating, shipping cost)

---

## 💬 Questions?

Feel free to open an issue or reach out to the maintainers. Happy deal hunting! 🎁
