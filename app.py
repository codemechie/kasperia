import asyncio
import logging
import time
from datetime import datetime

import streamlit as st

from contracts.models import AgentInput, ToolConfig
from tools import MockToolRegistry
from tools.scenarios import (
    all_ok,
    primary_fails_fallback_1_ok,
    primary_fails_both_fallbacks_ok,
    all_fail,
    all_timeout,
    slow_but_successful,
)
from orchestrator import ToolOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("Dashboard")

st.set_page_config(
    page_title="Kasperia Debug Canvas",
    layout="wide",
    initial_sidebar_state="expanded",
)

SCENARIOS = {
    "Happy Path — Primary Succeeds": all_ok(),
    "Fallback — Primary Fails, Fallback 1 Succeeds": primary_fails_fallback_1_ok(),
    "Fallback Chain — Primary+FB1 Fail, FB2 Succeeds": primary_fails_both_fallbacks_ok(),
    "Total Failure — All Tools Fail": all_fail(),
    "Slow — High Latency, Eventual Success": slow_but_successful(),
    "Timeout — Tools Time Out": all_timeout(),
}

MARKETS = ["sports", "ecommerce", "news", "general", "crypto"]


def init_state():
    if "result" not in st.session_state:
        st.session_state.result = None
    if "orchestrator" not in st.session_state:
        registry = MockToolRegistry()
        config = ToolConfig(max_retries=2, timeout_seconds=5)
        st.session_state.orchestrator = ToolOrchestrator(registry, config)
        st.session_state.registry = registry


def run_scenario(scenario_name: str, scenarios, query: str, market: str):
    logger.info(f"DASHBOARD TRIGGER: scenario={scenario_name!r} query={query!r} market={market!r}")
    st.write(f"Running **{scenario_name}**...")

    scenario = scenarios[scenario_name]
    orch: ToolOrchestrator = st.session_state.orchestrator
    agent_input = AgentInput(query=query, market=market)

    start = time.monotonic()
    result = asyncio.run(orch.run(agent_input, scenario))
    elapsed = (time.monotonic() - start) * 1000

    logger.info(
        f"DASHBOARD RESULT: status={result.status.value} "
        f"strategy={result.metadata.recovery_strategy} "
        f"payloads={len(result.result)} "
        f"latency={elapsed:.0f}ms"
    )

    st.session_state.result = {
        "scenario": scenario_name,
        "query": query,
        "market": market,
        "elapsed_ms": elapsed,
        "output": result,
        "timestamp": datetime.utcnow(),
    }


st.title("🔧 Kasperia Debug Canvas")
st.caption("Thin debugging dashboard for the multi-tool telemetry pipeline.")

init_state()

with st.sidebar:
    st.header("Controls")

    query = st.text_input("Query", value="Brazil")
    market = st.selectbox("Market", MARKETS, index=0)

    st.divider()
    st.subheader("Scenarios")

    for name in SCENARIOS:
        if st.button(name, use_container_width=True):
            run_scenario(name, SCENARIOS, query, market)

    st.divider()
    st.subheader("Session")

    if st.button("Clear Results", use_container_width=True):
        st.session_state.result = None
        st.rerun()

    seed_cache = st.checkbox("Seed cache on success", value=False, help="Copy successful results into CacheMock for future runs")

col1, col2 = st.columns([2, 1])

with col1:
    st.header("Audit Trail")

    if st.session_state.result is None:
        st.info("Run a scenario from the sidebar to see the audit trail.")
    else:
        data = st.session_state.result
        output = data["output"]

        status_color = {
            "success": "green",
            "partial_success": "orange",
            "failed": "red",
        }.get(output.status.value, "gray")

        meta = output.metadata

        st.markdown(f"**Status:** :{status_color}[{output.status.value.upper()}]")
        st.markdown(f"**Strategy:** `{meta.recovery_strategy.value if meta.recovery_strategy else 'N/A'}`")
        st.markdown(f"**Latency:** `{data['elapsed_ms']:.0f} ms`")
        st.markdown(f"**Query:** `{data['query']}`  **Market:** `{data['market']}`  **Tool Chain:** `{meta.recovery_strategy.value if meta.recovery_strategy else 'N/A'}`")

        st.divider()
        st.subheader("State Machine Flow")

        if hasattr(output, "metadata") and meta.reasoning_trace:
            st.code(meta.reasoning_trace, language="text")

        st.divider()
        st.subheader("Tools Called")

        if meta.tools_called:
            tool_data = {
                "Tool": [t.value for t in meta.tools_called],
                "Succeeded": ["✅" if t in meta.tools_succeeded else "❌" for t in meta.tools_called],
            }
            st.dataframe(tool_data, use_container_width=True)

        st.divider()
        st.subheader("Telemetry Payloads")

        if output.result:
            for i, p in enumerate(output.result):
                st.markdown(f"**Payload {i+1}** — `{p.source_system.value}`")
                st.json({
                    "entity_id": p.entity_id,
                    "metrics": p.metrics,
                    "signals": p.contextual_signals,
                    "status": p.status,
                    "confidence": p.confidence,
                })
        else:
            st.markdown("No payloads returned.")
            if output.error_message:
                st.error(output.error_message)

        if seed_cache and output.result:
            cache = st.session_state.registry.cache
            key = f"{data['market']}:{data['query'].lower().strip()}"
            for p in output.result:
                cache.seed(key, p)
            logger.info(f"DASHBOARD: seeded cache key={key!r} with {len(output.result)} payloads")

with col2:
    st.header("Raw Output")

    if st.session_state.result is None:
        st.info("Raw output will appear here.")
    else:
        data = st.session_state.result
        output = data["output"]

        raw = {
            "request_id": output.request_id,
            "status": output.status.value,
            "error_message": output.error_message,
            "metadata": {
                "agent_type": output.metadata.agent_type,
                "tools_called": [t.value for t in output.metadata.tools_called],
                "tools_succeeded": [t.value for t in output.metadata.tools_succeeded],
                "recovery_triggered": output.metadata.recovery_triggered,
                "recovery_strategy": output.metadata.recovery_strategy.value if output.metadata.recovery_strategy else None,
                "total_latency_ms": output.metadata.total_latency_ms,
            },
            "payload_count": len(output.result),
        }
        st.json(raw)

        st.divider()
        st.caption(f"Run at {data['timestamp'].strftime('%H:%M:%S.%f')[:-3]}")
