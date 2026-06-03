"""Unit tests for ToolExecutor — core orchestration primitive."""
import pytest
from datetime import datetime

from contracts.models import ToolName, ToolConfig, RecoveryStrategy, AgentStatus
from tools.base import ToolScenario, ToolScenarioMap
from tools.executor import ToolExecutor


class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_single_tool_succeeds(self, executor, scenarios_all_ok):
        report = await executor.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[],
            query="Brazil",
            market="sports",
            scenarios=scenarios_all_ok,
        )
        assert report.response is not None
        assert report.response.status == "success"
        assert len(report.response.data) >= 1
        assert report.strategy == RecoveryStrategy.PRIMARY_SUCCESS
        assert report.overall_status == AgentStatus.SUCCESS
        assert report.total_latency_ms > 0

    @pytest.mark.asyncio
    async def test_single_tool_fails(self, executor, scenarios_primary_fails):
        report = await executor.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[],
            query="Brazil",
            market="sports",
            scenarios=scenarios_primary_fails,
        )
        assert report.response is None
        assert report.strategy == RecoveryStrategy.FAILED_ALL_TOOLS
        assert report.overall_status == AgentStatus.FAILED
        assert len(report.recovery_log) >= 1

    @pytest.mark.asyncio
    async def test_fallback_chain_succeeds(self, executor, scenarios_primary_fails):
        report = await executor.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[ToolName.TAVILY_SEARCH, ToolName.SERPAPI_SEARCH, ToolName.LOCAL_CACHE],
            query="Brazil",
            market="sports",
            scenarios=scenarios_primary_fails,
        )
        assert report.response is not None
        assert report.response.status == "success"
        assert report.overall_status == AgentStatus.PARTIAL_SUCCESS
        assert report.strategy == RecoveryStrategy.SWITCHED_TO_FALLBACK_1

    @pytest.mark.asyncio
    async def test_all_tools_fail(self, executor):
        scenarios = {
            ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.TAVILY_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.SERPAPI_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.LOCAL_CACHE: ToolScenario(),
        }
        report = await executor.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[ToolName.TAVILY_SEARCH, ToolName.SERPAPI_SEARCH, ToolName.LOCAL_CACHE],
            query="Brazil",
            market="sports",
            scenarios=scenarios,
        )
        assert report.response is None
        assert report.strategy == RecoveryStrategy.FAILED_ALL_TOOLS
        assert report.overall_status == AgentStatus.FAILED

    @pytest.mark.asyncio
    async def test_timeout_propagation(self, executor):
        scenarios = {
            ToolName.API_FOOTBALL: ToolScenario(
                failure_mode="timeout", failure_probability=1.0, latency_range=(10.0, 15.0)
            ),
            ToolName.TAVILY_SEARCH: ToolScenario(),
        }
        report = await executor.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[ToolName.TAVILY_SEARCH],
            query="Brazil",
            market="sports",
            scenarios=scenarios,
        )
        assert report.response is not None
        assert report.overall_status == AgentStatus.PARTIAL_SUCCESS
        assert report.strategy == RecoveryStrategy.SWITCHED_TO_FALLBACK_1

    @pytest.mark.asyncio
    async def test_attempts_tracking(self, executor, scenarios_all_ok):
        report = await executor.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[],
            query="Brazil",
            market="sports",
            scenarios=scenarios_all_ok,
        )
        assert len(report.attempts) >= 1
        assert report.attempts[0]["tool"] == "api_football"
        assert report.attempts[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_recovery_log_on_failure(self, executor, scenarios_primary_fails):
        report = await executor.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[],
            query="Brazil",
            market="sports",
            scenarios=scenarios_primary_fails,
        )
        assert len(report.recovery_log) >= 1
        event = report.recovery_log[0]
        assert event.status == "failed"
        assert event.tool_attempted == ToolName.API_FOOTBALL

    @pytest.mark.asyncio
    async def test_recovery_log_on_success(self, executor, scenarios_all_ok):
        report = await executor.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[],
            query="Brazil",
            market="sports",
            scenarios=scenarios_all_ok,
        )
        assert len(report.recovery_log) >= 1
        event = report.recovery_log[0]
        assert event.status == "success"

    @pytest.mark.asyncio
    async def test_cache_only_as_fallback(self, executor, registry, sample_payload_sports):
        registry.cache.seed("sports:brazil", sample_payload_sports)
        scenarios = {
            ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.LOCAL_CACHE: ToolScenario(),
        }
        report = await executor.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[ToolName.LOCAL_CACHE],
            query="Brazil",
            market="sports",
            scenarios=scenarios,
        )
        assert report.response is not None
        assert len(report.response.data) == 1

    @pytest.mark.asyncio
    async def test_no_fallbacks_configured(self, executor, scenarios_primary_fails):
        report = await executor.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[],
            query="Brazil",
            market="sports",
            scenarios=scenarios_primary_fails,
        )
        assert report.response is None
        assert report.strategy == RecoveryStrategy.FAILED_ALL_TOOLS

    @pytest.mark.asyncio
    async def test_three_level_fallback(self, executor):
        scenarios = {
            ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.TAVILY_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.SERPAPI_SEARCH: ToolScenario(),
            ToolName.LOCAL_CACHE: ToolScenario(),
        }
        report = await executor.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[ToolName.TAVILY_SEARCH, ToolName.SERPAPI_SEARCH, ToolName.LOCAL_CACHE],
            query="Brazil",
            market="sports",
            scenarios=scenarios,
        )
        assert report.response is not None
        assert report.strategy == RecoveryStrategy.SWITCHED_TO_FALLBACK_2
        assert report.overall_status == AgentStatus.PARTIAL_SUCCESS

    def test_strategy_mapping(self, executor):
        assert executor._strategy_for(0) == RecoveryStrategy.PRIMARY_SUCCESS
        assert executor._strategy_for(1) == RecoveryStrategy.SWITCHED_TO_FALLBACK_1
        assert executor._strategy_for(2) == RecoveryStrategy.SWITCHED_TO_FALLBACK_2
        assert executor._strategy_for(3) == RecoveryStrategy.SWITCHED_TO_CACHE
        assert executor._strategy_for(4) == RecoveryStrategy.SYNTHESIS_REQUIRED
