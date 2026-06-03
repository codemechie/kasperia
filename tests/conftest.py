from datetime import datetime
from typing import Dict, List

import pytest

from contracts.models import (
    TelemetryPayload,
    ToolResponse,
    ToolName,
    AgentInput,
    AgentOutput,
    AgentStatus,
    AgentMetadata,
    RecoveryEvent,
    RecoveryStrategy,
    ToolConfig,
)
from tools import MockToolRegistry
from tools.base import ToolScenario, ToolScenarioMap
from tools.executor import ToolExecutor
from orchestrator.state_machine import RecoveryStateMachine
from orchestrator.orchestrator import ToolOrchestrator


# ============================================================================
# Fixtures: Data
# ============================================================================

@pytest.fixture
def sample_payload_sports() -> TelemetryPayload:
    return TelemetryPayload(
        source_system=ToolName.API_FOOTBALL,
        timestamp=datetime.utcnow(),
        entity_id="match_brazil_france_101",
        metrics={"home_score": 2, "away_score": 1},
        contextual_signals={
            "status": "LIVE",
            "league": "World Cup",
            "venue": "Stadium X",
            "home_team": "Brazil",
            "away_team": "France",
        },
        status="OK",
        confidence=0.95,
        latency_ms=142.0,
    )


@pytest.fixture
def sample_payload_news() -> TelemetryPayload:
    return TelemetryPayload(
        source_system=ToolName.TAVILY_SEARCH,
        timestamp=datetime.utcnow(),
        entity_id="search_brazil_advances_to_semi-finals",
        metrics={"num_results": 5},
        contextual_signals={
            "title": "Brazil Advances to Semi-Finals",
            "content": "In an exciting match...",
            "source_url": "https://sports-news.example.com/brazil",
        },
        status="OK",
        confidence=0.75,
        latency_ms=200.0,
    )


@pytest.fixture
def sample_payload_ecommerce() -> TelemetryPayload:
    return TelemetryPayload(
        source_system=ToolName.SERPAPI_SEARCH,
        timestamp=datetime.utcnow(),
        entity_id="serpapi_nike_air_max_270",
        metrics={"num_results": 3},
        contextual_signals={
            "title": "Nike Air Max 270",
            "snippet": "Buy Nike Air Max 270 at the best price",
            "source_url": "https://shop.example.com/nike-air-max-270",
            "position": 1,
        },
        status="OK",
        confidence=0.60,
        latency_ms=180.0,
    )


@pytest.fixture
def sample_tool_response(sample_payload_sports) -> ToolResponse:
    return ToolResponse(
        tool_name=ToolName.API_FOOTBALL,
        status="success",
        data=[sample_payload_sports],
        latency_ms=142.0,
        confidence=0.95,
    )


@pytest.fixture
def agent_input_sports() -> AgentInput:
    return AgentInput(query="Brazil", market="sports")


@pytest.fixture
def agent_input_ecommerce() -> AgentInput:
    return AgentInput(query="shoes", market="ecommerce")


@pytest.fixture
def agent_input_news() -> AgentInput:
    return AgentInput(query="technology", market="news")


@pytest.fixture
def agent_input_unknown() -> AgentInput:
    return AgentInput(query="anything", market="crypto")


# ============================================================================
# Fixtures: Components
# ============================================================================

@pytest.fixture
def registry() -> MockToolRegistry:
    return MockToolRegistry()


@pytest.fixture
def default_config() -> ToolConfig:
    return ToolConfig(max_retries=2, timeout_seconds=5.0)


@pytest.fixture
def executor(registry, default_config) -> ToolExecutor:
    return ToolExecutor(registry, default_config)


@pytest.fixture
def state_machine(registry, default_config) -> RecoveryStateMachine:
    return RecoveryStateMachine(registry, default_config)


@pytest.fixture
def orchestrator(registry, default_config) -> ToolOrchestrator:
    return ToolOrchestrator(registry, default_config)


# ============================================================================
# Fixtures: Scenario helpers
# ============================================================================

@pytest.fixture
def scenarios_all_ok() -> ToolScenarioMap:
    return {
        ToolName.API_FOOTBALL: ToolScenario(),
        ToolName.TAVILY_SEARCH: ToolScenario(),
        ToolName.SERPAPI_SEARCH: ToolScenario(),
        ToolName.LOCAL_CACHE: ToolScenario(),
    }


@pytest.fixture
def scenarios_primary_fails() -> ToolScenarioMap:
    return {
        ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
        ToolName.TAVILY_SEARCH: ToolScenario(),
        ToolName.SERPAPI_SEARCH: ToolScenario(),
        ToolName.LOCAL_CACHE: ToolScenario(),
    }
