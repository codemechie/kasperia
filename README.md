# Kasperia 🔧

> A **multi-tool telemetry pipeline** that orchestrates tool execution with automatic fallback, state-machine-driven recovery, and full audit trails. Built for LLM agents — no domain models, no external API dependencies.

[![Python 3.13+](https://img.shields.io/badge/Python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Debug%20Canvas-red.svg)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🚀 What is Kasperia?

Kasperia is a **resilient tool execution engine** that:

- 🧠 **Orchestrates multi-tool pipelines** — primary + fallback chains with automatic retry
- 🔁 **Self-heals via a 5-state machine** — `IDLE → PRIMARY → RECOVERY → FALLBACK → TERMINAL`
- 📋 **Generates full audit trails** — every transition, attempt, and failure logged for the UI
- 🎯 **Mock-first development** — all tools are simulated, zero network calls during development
- 🔌 **Generic telemetry schema** — every tool output becomes a `TelemetryPayload`. No domain models.
- 🖥️ **Live debugging canvas** — Streamlit dashboard triggers scenarios with one click

Ask Kasperia: *"Show me Brazil match scores"*, and it will:
1. Map `sports` → primary `API_FOOTBALL`, fallbacks `[TAVILY, SERPAPI, CACHE]`
2. Execute the tool chain through the state machine
3. Validate and return normalized telemetry data
4. Log every state transition to the terminal

---

## 🏗️ Architecture Overview

### Pipeline

```
AgentInput(query, market)
    │
    ▼
ToolOrchestrator
    │  1. Selects tool chain by market
    │  2. Hands off to state machine
    │
    ▼
RecoveryStateMachine (5 states)
    │  IDLE → PRIMARY (with retries)
    │       → RECOVERY (between attempts)
    │       → FALLBACK (chain)
    │       → TERMINAL (result or failure)
    │
    ▼
ToolExecutor
    │  Tries primary → fallbacks in order
    │  Returns ToolExecutionReport + RecoveryEvent[]
    │
    ▼
MockTool (no network calls)
    │  ApiFootballMock | TavilyMock | SerpApiMock | CacheMock
    │  Configurable: latency, failure mode, probability
    │
    ▼
validate_telemetry_batch() → AgentOutput
```

### The 5-State Machine

| State | What happens |
|---|---|
| **IDLE** | Awaiting input. Reset per request. |
| **PRIMARY** | Runs the primary tool. Retries up to `max_retries` times. |
| **RECOVERY** | Logs failure, prepares next attempt. |
| **FALLBACK** | Runs the fallback tool chain. |
| **TERMINAL** | Final — success or failure. No outgoing transitions. |

### Market → Tool Chain Mapping

| Market | Primary | Fallbacks |
|---|---|---|
| `sports` | `API_FOOTBALL` | `TAVILY`, `SERPAPI`, `CACHE` |
| `ecommerce` | `SERPAPI` | `TAVILY`, `CACHE` |
| `news` | `TAVILY` | `SERPAPI`, `CACHE` |
| `general` | `TAVILY` | `SERPAPI`, `CACHE` |
| `*` (unknown) | `TAVILY` | `SERPAPI`, `CACHE` |

Unknown markets fall back to `general` — never crashes on an unrecognized market string.

---

## ⚡ Key Features

### State-Machine Recovery
A 5-state machine drives execution with validated transitions. Invalid transitions are caught at runtime and logged. Retries, fallbacks, and final disposition are all tracked.

### Full Audit Trail
Every state transition, tool attempt, failure, and recovery generates an immutable `AuditEvent`. The UI renders these as a timeline. The `StateMachineResult` contains everything needed for observability.

### Generic Telemetry Schema
No domain models. Every tool output becomes a `TelemetryPayload` with `metrics`, `contextual_signals`, `status`, and `confidence`. Agents reason generically over this unified schema.

### Mock-First Development
All four tools are simulated with configurable latency, failure modes, and probabilities. Swap in real HTTP implementations later without changing the orchestration layer.

### Live Debug Canvas
A Streamlit dashboard lets you trigger any scenario with one click. See the audit trail, state transitions, tool results, and raw output — all while terminal logs stream in real time.

### Scenario Presets

| Scenario | Behavior |
|---|---|
| Happy Path | Primary succeeds, low latency |
| Fallback 1 | Primary fails → fallback succeeds |
| Fallback 2 | Primary + FB1 fail → FB2 succeeds |
| Total Failure | All tools fail |
| Slow | 1–3s latency, eventual success |
| Timeout | All tools time out |

---

## 📁 Project Structure

```
kasperia/
├── app.py                        # Streamlit debug canvas
├── orchestrator/
│   ├── orchestrator.py           # ToolOrchestrator — market→chain, pipeline entry
│   ├── state_machine.py          # RecoveryStateMachine — 5 states, audit trail
│   └── __init__.py
├── tools/
│   ├── base.py                   # MockTool ABC + ToolScenario config
│   ├── executor.py               # ToolExecutor — retry, fallback, recovery events
│   ├── scenarios.py              # Named scenario presets (all_ok, all_fail, etc.)
│   └── __init__.py               # MockToolRegistry + 4 mock implementations
├── contracts/
│   ├── models.py                 # TelemetryPayload, ToolResponse, AgentInput/Output
│   └── validators.py             # validate_telemetry_batch()
├── agents/
│   └── interpreter_agent.py      # Raw tool output → TelemetryPayload normalizer
├── utils/
│   ├── fetch.py                  # HTTP utility (preserved for future real tools)
│   └── __init__.py
├── concepts.md                   # Full architecture reference
└── README.md                     # This file
```

---

## 🔧 Getting Started

### Prerequisites

- **Python 3.13+**
- **Ollama** (optional — only needed for real LLM agents)

### Installation

```bash
git clone https://github.com/codemechie/kasperia.git
cd kasperia
pip install -r requirements.txt
streamlit run app.py
```

### Running the Debug Canvas

```bash
streamlit run app.py
```

Opens `http://localhost:8501`. The sidebar has:
- **Query** text field — what to search for
- **Market** dropdown — which tool chain to use
- **Scenario buttons** — instantly trigger any failure mode
- **Seed cache** — persist results into `CacheMock` for subsequent runs

### Triggering Scenarios

Every button click:
1. Constructs an `AgentInput` with your query + market
2. Runs the full pipeline through `ToolOrchestrator`
3. Renders the audit trail, state transitions, and telemetry payloads
4. Logs structured output to the terminal:

```
2026-06-02 [INFO] ToolOrchestrator: Orchestrating: query='Brazil' market='sports'
2026-06-02 [INFO] ToolOrchestrator: Tool chain: primary=api_football fallbacks=['tavily', 'serpapi', 'cache']
2026-06-02 [INFO] RecoveryStateMachine: idle → primary | Starting primary tool: api_football
2026-06-02 [INFO] ToolExecutor: Tool api_football succeeded (strategy: primary_success)
2026-06-02 [INFO] RecoveryStateMachine: primary → terminal | Primary succeeded on attempt 1
```

### Example: Programmatic Usage

```python
import asyncio
from tools import MockToolRegistry
from tools.scenarios import all_ok
from contracts.models import AgentInput, ToolConfig
from orchestrator import ToolOrchestrator

registry = MockToolRegistry()
orch = ToolOrchestrator(registry, ToolConfig(max_retries=2, timeout_seconds=5))

result = asyncio.run(orch.run(
    AgentInput(query="Brazil", market="sports"),
    all_ok(),
))

print(f"Status: {result.status.value}")
print(f"Strategy: {result.metadata.recovery_strategy}")
print(f"Payloads: {len(result.result)}")
```

---

## 📊 Data Flow

```
AgentInput(query="Brazil", market="sports")
    │
    ▼
ToolOrchestrator._select_chain("sports")
    │  → primary=API_FOOTBALL
    │  → fallbacks=[TAVILY, SERPAPI, CACHE]
    │
    ▼
RecoveryStateMachine.execute()
    │
    ├── Phase 1: PRIMARY ──► ToolExecutor(primary=API_FOOTBALL)
    │       │ success → TERMINAL ✓
    │       │ failure → RECOVERY → retry
    │
    ├── Phase 2: FALLBACK ──► ToolExecutor(primary=TAVILY, fallbacks=[SERPAPI, CACHE])
    │       │ success → TERMINAL ✓
    │       │ failure → TERMINAL ✗
    │
    └── Phase 3: TERMINAL
            │ StateMachineResult(response, strategy, audit_trail)
            ▼
    ToolOrchestrator
            │ validate_telemetry_batch()
            │ inject _market / _query context
            ▼
    AgentOutput(status, result=[TelemetryPayload...])
```

---

## 🔐 Safety & Reliability

- **Validated transitions** — state machine rejects illegal moves at runtime
- **Immutable contracts** — `dataclass(frozen=True)` everywhere. No mutation surprises.
- **Observable recovery** — every failure produces a `RecoveryEvent`. Full chain traceable.
- **Graceful fallbacks** — primary fails → try cache → try synthesis → fail with clear message
- **Mock-first** — real APIs never called during development. Swap in real tools when ready.

---

## 🤝 Contributing

Areas for enhancement:

- Real HTTP tool implementations (swap `MockTool` subclasses)
- LLM-powered orchestrator (use `InterpreterAgent` for raw data normalization)
- Persistent state (SQLite/Redis for `ToolConfig`)
- Additional scenario presets
- Web UI for multi-turn agent conversations

---

## 📄 License

MIT License — See [LICENSE](LICENSE) for details.

---

## 🎯 Roadmap

- [x] Multi-tool orchestration with fallback chains
- [x] 5-state recovery machine with audit trail
- [x] Mock tool layer with configurable failure modes
- [x] Streamlit debug canvas
- [x] Generic telemetry schema (no domain models)
- [ ] Real HTTP tool implementations
- [ ] LLM agent integration (Ollama)
- [ ] Persistent state storage

---

## 💬 Questions?

Open an issue or reach out to the maintainers. Happy building! 🔧
