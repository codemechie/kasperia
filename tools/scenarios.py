from typing import Dict

from contracts.models import ToolName
from tools.base import ToolScenario, ToolScenarioMap


def all_ok() -> ToolScenarioMap:
    return {
        ToolName.API_FOOTBALL: ToolScenario(),
        ToolName.TAVILY_SEARCH: ToolScenario(),
        ToolName.SERPAPI_SEARCH: ToolScenario(),
        ToolName.LOCAL_CACHE: ToolScenario(),
    }


def primary_fails_fallback_1_ok() -> ToolScenarioMap:
    return {
        ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
        ToolName.TAVILY_SEARCH: ToolScenario(),
        ToolName.SERPAPI_SEARCH: ToolScenario(),
        ToolName.LOCAL_CACHE: ToolScenario(),
    }


def primary_fails_both_fallbacks_ok() -> ToolScenarioMap:
    return {
        ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
        ToolName.TAVILY_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
        ToolName.SERPAPI_SEARCH: ToolScenario(),
        ToolName.LOCAL_CACHE: ToolScenario(),
    }


def all_fail() -> ToolScenarioMap:
    return {
        ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
        ToolName.TAVILY_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
        ToolName.SERPAPI_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
        ToolName.LOCAL_CACHE: ToolScenario(),
    }


def all_timeout() -> ToolScenarioMap:
    return {
        ToolName.API_FOOTBALL: ToolScenario(failure_mode="timeout", failure_probability=1.0, latency_range=(5.0, 10.0)),
        ToolName.TAVILY_SEARCH: ToolScenario(failure_mode="timeout", failure_probability=1.0, latency_range=(5.0, 10.0)),
        ToolName.SERPAPI_SEARCH: ToolScenario(failure_mode="timeout", failure_probability=1.0, latency_range=(5.0, 10.0)),
        ToolName.LOCAL_CACHE: ToolScenario(),
    }


def partial_success(failure_prob: float = 0.5) -> ToolScenarioMap:
    return {
        ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=failure_prob),
        ToolName.TAVILY_SEARCH: ToolScenario(failure_mode="error", failure_probability=failure_prob),
        ToolName.SERPAPI_SEARCH: ToolScenario(failure_mode="error", failure_probability=failure_prob),
        ToolName.LOCAL_CACHE: ToolScenario(),
    }


def slow_but_successful() -> ToolScenarioMap:
    return {
        ToolName.API_FOOTBALL: ToolScenario(latency_range=(1.0, 3.0)),
        ToolName.TAVILY_SEARCH: ToolScenario(latency_range=(1.0, 3.0)),
        ToolName.SERPAPI_SEARCH: ToolScenario(latency_range=(1.0, 3.0)),
        ToolName.LOCAL_CACHE: ToolScenario(),
    }
