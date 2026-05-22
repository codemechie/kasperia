You are a senior technical writer. Write a professional README.md for the project described below.

## Project: Kasperia

### What it is
An AI-agent that searches e-commerce websites for the best deals. It uses a multi-agent architecture with two LLM roles (orchestrator + code-gen/debug) running via Ollama (Qwen 2.5), an MCP tool server (FastMCP) for the data-fetching layer, and a self-healing pipeline that auto-generates site-specific scrapers on demand — with automatic error recovery.

### Architecture (local & runtime)

#### Two LLM agents (three roles)
1. **Orchestrator** (`agent.py`) — User-facing Qwen that decides which store to query based on a natural language prompt. Calls the `search_products(query, domain)` tool with input validation.
2. **Code-Gen Agent** (`worker.py`) — Background Qwen that reverse-engineers a store's DOM into a runnable Python scraper class.
3. **Debugging Agent** (`worker.py`) — Same background worker, second LLM role: receives broken code + error traceback and patches syntax/import errors, retrying up to 3 times.

#### 3-layer server lookup (`server.py`)
- **Layer 1 — Cache:** In-memory dict hit returns instantly.
- **Layer 2 — Static Scraper:** Registered `BaseScraper` subclass handles the domain.
- **Layer 3 — Fallback + Background Build:** Generic JSON-LD/OG meta parser (with domain normalization) returns initial results immediately, while `state.queue` notifies the worker to generate a dedicated scraper.

#### Self-healing worker pipeline (`worker.py`)
1. `fetch_target_dom_sample()` — Lightweight HTTP GET to the store (tries 5 search URL patterns + homepage fallback, follows redirects), extracts ~2k chars of clean DOM.
2. `run_llm_codegen_agent()` — Feeds the DOM sample to Ollama, which returns a Python class `Scraper` (strips markdown fences).
3. **Self-healing loop** (max 3 attempts):
   - `load_agent_scraper()` — Isolated evaluator (`scrapers/evaluator.py`) compiles the code in a sandboxed module, validates the `Scraper` class exists, instantiates it, and live-binds it to `state.scraper_registry`.
   - **Valid** → write `.py` to `scrapers/generated/`, clean up debug dumps, break. Write failures are non-fatal (increment retry counter + continue).
   - **Invalid** → dump faulty code to `scrapers/debug_dump/` (wrapped in try/except for resilience), call `run_llm_debugging_agent()` with structured error trace, retry.
   - All attempts exhausted → log and abandon.
4. Marks job done via `state.queue.task_done()` (guaranteed by `finally`).

#### State container (`state.py`)
In-memory `AppState` with: `scraper_registry`, `cache`, `asyncio.Queue`, `asyncio.Lock`.

#### Startup
`main.py` boots the FastMCP server with a lifespan hook that auto-starts the background worker.

#### Testing
`test_query.py` — end-to-end pipeline verification: triggers a Layer 3 miss, waits for the background build, then verifies Layer 2 hit on retry. Wrapped in try/except/finally for clean shutdown.

### Key files
```
├── main.py                  # Entrypoint, graceful lifecycle
├── server.py                # FastMCP server, search_products tool, fallback parser (domain-normalized)
├── agent.py                 # Orchestrator LLM client (with input validation)
├── worker.py                # Background worker: DOM fetch → code-gen → self-healing loop → deploy
├── state.py                 # In-memory AppState container
├── test_query.py            # End-to-end pipeline test
└── scrapers/
    ├── base.py              # BaseScraper ABC
    ├── evaluator.py         # Isolated code compiler/validator (returns dict with error context)
    ├── schema.py            # Pydantic ProductDeal model
    ├── nike.py              # Nike scraper (adapted to BaseScraper + httpx)
    ├── adidas.py            # Adidas scraper (adapted to BaseScraper + httpx)
    ├── __init__.py          # Registry bootstrap: auto-registers static scrapers + boot-scans generated/
    ├── generated/           # Persisted code-gen artifacts (disk-backed, survive restarts)
    └── debug_dump/          # Faulty code staging (auto-cleaned on successful retry)
```

### USP (Unique Selling Points)
- **Self-healing scrapers with automatic recovery:** When a store isn't supported, the system auto-generates a custom scraper via LLM code-gen. If the generated code fails validation, a debugging agent patches it automatically — up to 3 attempts before giving up.
- **Dual-agent architecture (three roles):** One LLM handles user intent, another handles code generation and debugging — clean separation of concerns with robust error recovery.
- **Isolated code execution:** LLM-generated Python is compiled in a sandboxed module scope, preventing corrupted code from poisoning core system memory. The evaluator returns structured `{"success": True/False, "error": "..."}` dicts for precise failure feedback.
- **Instant fallback + non-blocking build:** Even for unsupported stores, a generic JSON-LD/OG meta parser returns results immediately while the dedicated scraper is being built in the background.
- **Resilient file I/O:** Write failures are non-fatal — OSErrors in the save or debug-dump paths are caught and handled gracefully without aborting the build loop.
- **Zero API keys:** No external search APIs — pure HTTP + BeautifulSoup + local Ollama.

### Style requirements
- Modern, clean markdown with emoji section headers (🚀, 🏗️, ⚡, etc.)
- A clear "How it works" section with a flow diagram (ASCII or Mermaid)
- Badges: Python 3.12+, FastMCP, Ollama
- Tone: professional but approachable — avoid jargon overflow
- Keep it concise: engineers should grasp the architecture in under 2 minutes

Write the complete README.md now.
