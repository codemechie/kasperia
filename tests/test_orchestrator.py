"""Unit tests for ToolOrchestrator — pipeline entry point."""
import pytest
from datetime import datetime

from contracts.models import (
    AgentInput,
    AgentOutput,
    AgentStatus,
    ToolName,
    RecoveryStrategy,
    ToolConfig,
)
from tools.base import ToolScenario


class TestToolOrchestrator:
    @pytest.mark.asyncio
    async def test_sports_market_success(self, orchestrator, scenarios_all_ok, agent_input_sports):
        output = await orchestrator.run(agent_input_sports, scenarios_all_ok)
        assert isinstance(output, AgentOutput)
        assert output.status == AgentStatus.SUCCESS
        assert len(output.result) >= 1
        assert output.metadata.recovery_strategy == RecoveryStrategy.PRIMARY_SUCCESS
        assert output.agent_id == "tool_orchestrator"

    @pytest.mark.asyncio
    async def test_sports_market_with_scenarios(self, orchestrator, scenarios_primary_fails, agent_input_sports):
        output = await orchestrator.run(agent_input_sports, scenarios_primary_fails)
        assert output.status == AgentStatus.PARTIAL_SUCCESS
        assert len(output.result) >= 1

    @pytest.mark.asyncio
    async def test_ecommerce_market(self, orchestrator, scenarios_all_ok, agent_input_ecommerce):
        output = await orchestrator.run(agent_input_ecommerce, scenarios_all_ok)
        assert output.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL_SUCCESS)
        assert len(output.result) >= 1

    @pytest.mark.asyncio
    async def test_news_market(self, orchestrator, scenarios_all_ok, agent_input_news):
        output = await orchestrator.run(agent_input_news, scenarios_all_ok)
        assert output.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL_SUCCESS)
        assert len(output.result) >= 1

    @pytest.mark.asyncio
    async def test_unknown_market_falls_back_to_general(self, orchestrator, scenarios_all_ok, agent_input_unknown):
        output = await orchestrator.run(agent_input_unknown, scenarios_all_ok)
        assert output.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL_SUCCESS)
        assert len(output.result) >= 1

    @pytest.mark.asyncio
    async def test_all_tools_fail_returns_failed(self, orchestrator, agent_input_sports):
        scenarios = {
            ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.TAVILY_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.SERPAPI_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.LOCAL_CACHE: ToolScenario(),
        }
        output = await orchestrator.run(agent_input_sports, scenarios)
        assert output.status == AgentStatus.FAILED
        assert output.result == []
        assert output.error_message is not None

    @pytest.mark.asyncio
    async def test_output_contains_metadata(self, orchestrator, scenarios_all_ok, agent_input_sports):
        output = await orchestrator.run(agent_input_sports, scenarios_all_ok)
        meta = output.metadata
        assert meta.agent_type == "orchestrator"
        assert ToolName.API_FOOTBALL in meta.tools_called
        assert meta.total_latency_ms > 0
        assert meta.started_at is not None
        assert meta.completed_at is not None

    @pytest.mark.asyncio
    async def test_recovery_triggered_flag(self, orchestrator, agent_input_sports, scenarios_all_ok):
        output = await orchestrator.run(agent_input_sports, scenarios_all_ok)
        assert output.metadata.recovery_triggered is False

    @pytest.mark.asyncio
    async def test_partial_success_sets_recovery_flag(self, orchestrator, scenarios_primary_fails, agent_input_sports):
        output = await orchestrator.run(agent_input_sports, scenarios_primary_fails)
        assert output.status == AgentStatus.PARTIAL_SUCCESS

    @pytest.mark.asyncio
    async def test_request_id_passthrough(self, orchestrator, scenarios_all_ok, agent_input_sports):
        output = await orchestrator.run(agent_input_sports, scenarios_all_ok)
        assert output.request_id == agent_input_sports.request_id

    @pytest.mark.asyncio
    async def test_is_successful_property(self, orchestrator, scenarios_all_ok, agent_input_sports):
        output = await orchestrator.run(agent_input_sports, scenarios_all_ok)
        assert output.is_successful is True

    @pytest.mark.asyncio
    async def test_is_successful_on_failure(self, orchestrator, agent_input_sports):
        scenarios = {
            ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.TAVILY_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.SERPAPI_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.LOCAL_CACHE: ToolScenario(),
        }
        output = await orchestrator.run(agent_input_sports, scenarios)
        assert output.is_successful is False

    def test_select_chain_sports(self, orchestrator):
        chain = orchestrator._select_chain("sports")
        assert chain.primary == ToolName.API_FOOTBALL
        assert ToolName.TAVILY_SEARCH in chain.fallbacks
        assert ToolName.SERPAPI_SEARCH in chain.fallbacks
        assert ToolName.LOCAL_CACHE in chain.fallbacks

    def test_select_chain_ecommerce(self, orchestrator):
        chain = orchestrator._select_chain("ecommerce")
        assert chain.primary == ToolName.SERPAPI_SEARCH
        assert ToolName.TAVILY_SEARCH in chain.fallbacks
        assert ToolName.LOCAL_CACHE in chain.fallbacks

    def test_select_chain_news(self, orchestrator):
        chain = orchestrator._select_chain("news")
        assert chain.primary == ToolName.TAVILY_SEARCH

    def test_select_chain_general(self, orchestrator):
        chain = orchestrator._select_chain("general")
        assert chain.primary == ToolName.TAVILY_SEARCH

    def test_select_chain_unknown_market(self, orchestrator):
        chain = orchestrator._select_chain("unknown_market")
        assert chain.primary == ToolName.TAVILY_SEARCH
        assert ToolName.SERPAPI_SEARCH in chain.fallbacks

    def test_select_chain_case_insensitive(self, orchestrator):
        chain = orchestrator._select_chain("SPORTS")
        assert chain.primary == ToolName.API_FOOTBALL

    def test_select_chain_whitespace_insensitive(self, orchestrator):
        chain = orchestrator._select_chain("  sports  ")
        assert chain.primary == ToolName.API_FOOTBALL

    @pytest.mark.asyncio
    async def test_tool_config_respected(self, registry, agent_input_sports, scenarios_all_ok):
        config = ToolConfig(max_retries=0, timeout_seconds=30.0)
        from orchestrator import ToolOrchestrator
        orch = ToolOrchestrator(registry, config)
        output = await orch.run(agent_input_sports, scenarios_all_ok)
        assert output.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL_SUCCESS)

    @pytest.mark.asyncio
    async def test_statelessness(self, orchestrator, scenarios_all_ok):
        def make_input():
            return AgentInput(query="Brazil", market="sports")
        output1 = await orchestrator.run(make_input(), scenarios_all_ok)
        output2 = await orchestrator.run(make_input(), scenarios_all_ok)
        assert output1.request_id != output2.request_id

    @pytest.mark.asyncio
    async def test_error_details_on_failure(self, orchestrator, agent_input_sports):
        scenarios = {
            ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.TAVILY_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.SERPAPI_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.LOCAL_CACHE: ToolScenario(),
        }
        output = await orchestrator.run(agent_input_sports, scenarios)
        assert output.error_details is not None
        assert output.error_details["market"] == "sports"
        assert output.error_details["query"] == "Brazil"
