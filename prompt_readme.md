You are a senior technical writer. Write a professional README.md for the project described below.

## Project: Kasperia

### What it is
An AI-agent that searches e-commerce websites for the best deals. It uses a multi-agent architecture with two LLM roles (orchestrator + code-gen) running via Ollama (Qwen 2.5), an MCP tool server (FastMCP) for the data-fetching layer, and a self-healing pipeline that auto-generates site-specific scrapers on demand.

### Architecture (local & runtime)

#### Two LLM agents
1. **Orchestrator** (`agent.py`) — User-facing Qwen that decides which store to query based on a natural language prompt. Calls the `search_products(query, domain)` tool.
2. **Code-Gen Agent** (`worker.py`) — Background Qwen that reverse-engineers a store's DOM into a runnable Python scraper class.

#### 3-layer server lookup (`server.py`)
- **Layer 1 — Cache:** In-memory dict hit returns instantly.
- **Layer 2 — Static Scraper:** Registered BaseScraper subclass handles the domain.
- **Layer 3 — Fallback + Background Build:** Generic JSON-LD/OG meta parser returns initial results immediately, while `state.queue` notifies the worker to generate a dedicated scraper.

#### Worker pipeline (`worker.py`)
1. `fetch_target_dom_sample()` — Lightweight HTTP GET to the store, extracts ~5k chars of body text.
2. `run_llm_codegen_agent()` — Feeds the DOM sample to Ollama, which returns a Python class `Scraper`.
3. `load_agent_scraper()` — Isolated evaluator (`scrapers/evaluator.py`) compiles the code in a sandboxed module, validates the `Scraper` class exists, instantiates it, and live-binds it to `state.scraper_registry` for future Layer-2 hits.

#### State container (`state.py`)
In-memory `AppState` with: `scraper_registry`, `cache`, `asyncio.Queue`, `asyncio.Lock`.

#### Startup
`main.py` boots the FastMCP server with a lifespan hook that auto-starts the background worker.

### Key files
```
├── main.py                  # Entrypoint, graceful lifecycle
├── server.py                # FastMCP server, search_products tool, fallback parser
├── agent.py                 # Orchestrator LLM client
├── worker.py                # Background worker: DOM fetch → code-gen → validate → deploy
├── state.py                 # In-memory AppState container
└── scrapers/
    ├── base.py              # BaseScraper ABC
    ├── evaluator.py         # Isolated code compiler/validator
    ├── schema.py            # Pydantic ProductDeal model
    ├── nike.py              # Nike scraper (legacy, not yet adapted)
    ├── adidas.py            # Adidas scraper (legacy, not yet adapted)
    └── __init__.py          # Legacy SCRAPERS dict
```

### USP (Unique Selling Points)
- **Self-healing scrapers:** When a store isn't supported, the system auto-generates a custom scraper via LLM code-gen — no manual coding.
- **Dual-agent architecture:** One LLM handles user intent, another handles code generation — clean separation of concerns.
- **Isolated code execution:** LLM-generated Python is compiled in a sandboxed module scope, preventing corrupted code from poisoning core system memory.
- **Instant fallback:** Even for unsupported stores, a generic JSON-LD/OG meta parser returns results immediately while the dedicated scraper is being built.
- **Zero API keys:** No external search APIs — pure HTTP + BeautifulSoup + local Ollama.

### Style requirements
- Modern, clean markdown with emoji section headers (🚀, 🏗️, ⚡, etc.)
- A clear "How it works" section with a flow diagram (ASCII or Mermaid)
- Badges: Python 3.12+, FastMCP, Ollama
- Tone: professional but approachable — avoid jargon overflow
- Keep it concise: engineers should grasp the architecture in under 2 minutes

Write the complete README.md now.
