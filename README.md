# Kasperia

> An AI-powered agent that searches e-commerce websites for the best deals in real-time.

[![Python Version](https://img.shields.io/badge/Python-3.12%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FastMCP](https://img.shields.io/badge/FastMCP-Server-00a8e8)](https://github.com/jlowell/fastmcp)
[![Ollama](https://img.shields.io/badge/Ollama-Qwen%202.5-FF6B35)](https://ollama.ai)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 🎯 What is Kasperia?

Kasperia is an autonomous AI agent that discovers and aggregates product deals across e-commerce platforms. Instead of manually hunting through websites, you describe what you're looking for in natural language, and Kasperia:

1. **Understands** your intent via an orchestrator LLM
2. **Searches** the most relevant e-commerce sites
3. **Generates custom scrapers on-the-fly** for unsupported stores
4. **Self-heals** when scrapers fail, automatically fixing errors up to 3 times
5. **Returns** the best deals with zero external API keys

## 🚀 Key Features

### ⚡ Instant Fallback + Non-Blocking Build
Even for unsupported stores, a generic meta-tag parser returns results **immediately** while a dedicated scraper builds in the background. On your next query, Kasperia uses the newly generated scraper for faster, more accurate results.

### 🧠 Self-Healing Scrapers
Generated code fails? No problem. The debugging agent automatically analyzes the error trace and patches syntax/import issues—retrying up to 3 times before giving up. Dead simple, bulletproof.

### 🏗️ Dual-Agent Architecture (Three Roles)
- **Orchestrator** — User-facing LLM that parses natural language queries and routes them to the right store
- **Code-Gen Agent** — Reverse-engineers a store's DOM into a working Python scraper class
- **Debugging Agent** — Receives broken code + traceback, patches errors, and retries

Clean separation of concerns. Zero coupling.

### 🔒 Isolated Code Execution
LLM-generated Python runs in a sandboxed module scope. Corrupted code can't poison core system memory. The evaluator returns structured error dicts for precise failure feedback.

### 🌐 Zero External APIs
- No Selenium/Playwright overhead
- No paid search API subscriptions
- Pure HTTP + BeautifulSoup + local Ollama
- Lightweight, fast, and fully offline-capable

### 💾 Persistent Scraper Cache
Generated scrapers live on disk in `scrapers/generated/` and survive app restarts. Your first query builds the scraper; subsequent queries are blazingly fast.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│  User Query (Natural Language)                      │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
        ┌─────────────────────┐
        │  Orchestrator Agent │ (agent.py)
        │  Calls: search_products(query, domain)
        └─────────┬───────────┘
                  │
      ┌───────────┴───────────┐
      │                       │
      ▼                       ▼
 Layer 1: Cache          Layer 2: Static
 (in-memory dict)        Scraper Registry
      │                       │
      └──────┬────────────┬───┘
             │            │
         Hit │            │ Hit
             │            │
      ┌──────▼┐      ┌────▼──────┐
      │Return │      │  Return   │
      │Results│      │  Results  │
      └───────┘      └───────────┘
                          │
                          │ Miss
                          ▼
                     Layer 3: Fallback
                     + Background Build
                     ├─ Generic meta-tag parser
                     │  (JSON-LD, OG tags)
                     └─ Queue worker for
                        custom scraper generation
                             │
                             ▼
                     ┌──────────────────┐
                     │  Worker Process  │
                     ├──────────────────┤
                     │ 1. DOM Fetch     │
                     │ 2. Code-Gen      │
                     │ 3. Validation    │
                     │ 4. Self-Healing  │
                     │ 5. Deploy        │
                     └──────────────────┘
```

### Three-Layer Server Lookup

| Layer | Mechanism | Speed | Accuracy |
|-------|-----------|-------|----------|
| **1 — Cache** | In-memory dict lookup | Instant | Perfect (cached result) |
| **2 — Static Scraper** | Registered `BaseScraper` subclass | Fast | High (hand-tuned) |
| **3 — Fallback + Build** | Generic meta-tag parser + background code-gen | Immediate | Medium (initial) → High (after build) |

### Self-Healing Worker Pipeline

```python
fetch_target_dom_sample()
    ↓ (lightweight HTTP, tries 5 search patterns + homepage fallback)
run_llm_codegen_agent()
    ↓ (Ollama generates Python Scraper class)
Self-Healing Loop (max 3 attempts):
    ├─ load_agent_scraper() → Sandbox compile & validate
    ├─ Valid? → Write to scrapers/generated/, success ✓
    └─ Invalid? → Dump to debug_dump/, call run_llm_debugging_agent(), retry
    ↓ (all attempts exhausted or successful)
state.queue.task_done() → Job marked complete
```

---

## 📂 Project Structure

```
kasperia/
├── main.py                    # Entrypoint, graceful lifecycle management
├── server.py                  # FastMCP server + search_products tool
├── agent.py                   # Orchestrator LLM client (input validation)
├── worker.py                  # Background worker: fetch → codegen → heal → deploy
├── state.py                   # In-memory AppState container (registry, cache, queue)
├── test_query.py              # End-to-end pipeline verification
│
└── scrapers/
    ├── base.py                # BaseScraper abstract base class
    ├── evaluator.py           # Isolated code compiler/validator
    ├── schema.py              # Pydantic ProductDeal model
    ├── nike.py                # Nike scraper (static, hand-tuned)
    ├── adidas.py              # Adidas scraper (static, hand-tuned)
    ├── __init__.py            # Registry bootstrap + auto-scan generated/
    ├── generated/             # Persisted LLM-generated scrapers (survives restarts)
    └── debug_dump/            # Faulty code staging (auto-cleaned on success)
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- [Ollama](https://ollama.ai) with Qwen 2.5 model running locally
- `pip` (or your preferred package manager)

### Installation

```bash
# Clone the repository
git clone https://github.com/codemechie/kasperia.git
cd kasperia

# Install dependencies
pip install -r requirements.txt

# Ensure Ollama is running
ollama serve
```

### Usage

```bash
# Run the FastMCP server (starts worker background thread automatically)
python main.py

# In another terminal, run the end-to-end test
python test_query.py
```

The test will:
1. Trigger a Layer 3 miss (no static scraper for the target domain)
2. Wait for the background worker to generate a custom scraper
3. Retry the query to verify the Layer 2 cache hit

---

## 🔧 How It Works

### 1️⃣ User Query → Orchestrator Agent
You ask: *"Show me Nike shoes under $100 with good reviews"*

The orchestrator parses your intent, determines the relevant store(s), and calls the `search_products(query, domain)` tool.

### 2️⃣ Three-Layer Lookup
- **Layer 1 (Cache)**: Is this store already in memory? Return instantly.
- **Layer 2 (Static Registry)**: Is there a hand-tuned scraper for this store? Use it.
- **Layer 3 (Fallback)**: Neither? Parse generic meta tags and queue a background build.

### 3️⃣ Background Worker (if needed)
```
Fetch DOM → LLM CodeGen → Compile & Validate → Self-Heal (if errors) → Deploy
```

The worker:
- Fetches a sample of the target store's DOM (2k chars, cleaned HTML)
- Feeds it to Ollama (Qwen 2.5) to generate a `Scraper` class
- Compiles the code in an isolated sandbox
- If validation fails, calls the debugging agent to fix errors (retry up to 3 times)
- Writes the final scraper to `scrapers/generated/` on success

### 4️⃣ Next Query (Same Store)
Layer 2 cache hit. Results returned instantly using the generated scraper.

---

## 🛡️ Resilience & Error Handling

- **Non-fatal write failures**: OSErrors saving to disk don't abort the build loop
- **Sandbox isolation**: Corrupted LLM code can't crash the main process
- **Structured error feedback**: The evaluator returns `{"success": bool, "error": "..."}` dicts
- **Automatic retries**: Up to 3 self-healing attempts before graceful fallback
- **Clean shutdown**: `finally` blocks in the worker ensure `task_done()` is always called

---

## 📊 State Management

All application state lives in a single `AppState` container (`state.py`):

```python
@dataclass
class AppState:
    scraper_registry: dict[str, BaseScraper]    # Cached scraper instances
    cache: dict[str, list[ProductDeal]]         # Search result cache
    queue: asyncio.Queue                         # Background job queue
    lock: asyncio.Lock                          # Thread-safe mutations
```

---

## 🧪 Testing

```bash
python test_query.py
```

End-to-end verification:
- Triggers a Layer 3 miss for a new store
- Waits for the background build to complete
- Verifies the Layer 2 cache hit on retry
- Graceful exception handling and cleanup

---

## 🤝 Contributing

Contributions are welcome! To add a new static scraper:

1. Create a new file in `scrapers/` (e.g., `amazon.py`)
2. Subclass `BaseScraper` and implement `search(query: str) -> list[ProductDeal]`
3. Register it in `scrapers/__init__.py`
4. Add tests to `test_query.py`

For bug reports or feature requests, open an issue on GitHub.

---

## 📝 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## 💡 Why Kasperia?

In a world of fragmented e-commerce platforms, hunting for deals is tedious. Kasperia automates it with:

- **Zero external dependencies**: No API keys, no rate limits, no vendor lock-in
- **Instant results**: Even for unsupported stores, you get results immediately
- **Self-improving**: Each new store generates a persistent, reusable scraper
- **Bulletproof recovery**: Broken scrapers fix themselves

Query once. Kasperia learns. Query again. Kasperia is faster.

---

**Built with ❤️ using Python, FastMCP, Ollama, and a sprinkle of AI magic.**
