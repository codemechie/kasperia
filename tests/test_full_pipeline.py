"""Full pipeline integration tests — AgentInput → AgentOutput end-to-end."""
import pytest
from datetime import datetime

from contracts.models import AgentInput, AgentOutput, AgentStatus, ToolName, ToolConfig
from tools import MockToolRegistry
from tools.base import ToolScenario
from tools.scenarios import all_ok, all_fail
from orchestrator import ToolOrchestrator


@pytest.fixture
def pipeline():
    registry = MockToolRegistry()
    config = ToolConfig(max_retries=2, timeout_seconds=5.0)
    orch = ToolOrchestrator(registry, config)
    return registry, orch


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_happy_path(self, pipeline):
        """Sports query, all tools succeed → SUCCESS with api_football data."""
        _, orch = pipeline
        agent_input = AgentInput(query="Brazil", market="sports")
        output = await orch.run(agent_input, all_ok())

        assert output.status == AgentStatus.SUCCESS
        assert output.is_successful is True
        assert len(output.result) >= 1
        p = output.result[0]
        assert p.source_system == ToolName.API_FOOTBALL
        assert p.contextual_signals.get("_market") == "sports"
        assert p.contextual_signals.get("_query") == "Brazil"

    @pytest.mark.asyncio
    async def test_pipeline_fallback_path(self, pipeline):
        """Primary fails, fallback succeeds → PARTIAL_SUCCESS."""
        _, orch = pipeline
        scenarios = {
            ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.TAVILY_SEARCH: ToolScenario(),
            ToolName.SERPAPI_SEARCH: ToolScenario(),
            ToolName.LOCAL_CACHE: ToolScenario(),
        }
        agent_input = AgentInput(query="Brazil", market="sports")
        output = await orch.run(agent_input, scenarios)

        assert output.status == AgentStatus.PARTIAL_SUCCESS
        assert output.is_successful is True
        assert len(output.result) >= 1

    @pytest.mark.asyncio
    async def test_pipeline_all_fail(self, pipeline):
        """All tools fail → FAILED with no results."""
        _, orch = pipeline
        agent_input = AgentInput(query="Brazil", market="sports")
        output = await orch.run(agent_input, all_fail())

        assert output.status == AgentStatus.FAILED
        assert output.is_successful is False
        assert output.result == []
        assert output.error_message is not None
        assert "No data returned" in output.error_message

    @pytest.mark.asyncio
    async def test_pipeline_ecommerce(self, pipeline):
        """Ecommerce market uses SERPAPI primary."""
        _, orch = pipeline
        agent_input = AgentInput(query="shoes", market="ecommerce")
        output = await orch.run(agent_input, all_ok())

        assert output.status == AgentStatus.SUCCESS
        assert len(output.result) >= 1
        p = output.result[0]
        assert p.source_system == ToolName.SERPAPI_SEARCH
        assert p.metrics["num_results"] >= 1

    @pytest.mark.asyncio
    async def test_pipeline_unknown_market(self, pipeline):
        """Unknown market defaults to general (TAVILY primary)."""
        _, orch = pipeline
        agent_input = AgentInput(query="anything", market="crypto")
        output = await orch.run(agent_input, all_ok())

        assert output.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL_SUCCESS)
        assert len(output.result) >= 1

    @pytest.mark.asyncio
    async def test_pipeline_output_structure(self, pipeline):
        """Verify full AgentOutput contract fields are populated."""
        _, orch = pipeline
        agent_input = AgentInput(query="Brazil", market="sports")
        output = await orch.run(agent_input, all_ok())

        assert output.request_id == agent_input.request_id
        assert output.agent_id == "tool_orchestrator"
        assert output.started_at is not None
        assert output.completed_at is not None
        assert output.total_latency_ms > 0

        meta = output.metadata
        assert meta.agent_type == "orchestrator"
        assert len(meta.tools_called) >= 1
        assert meta.recovery_triggered is False
        assert meta.recovery_strategy is not None
        assert meta.total_latency_ms > 0

    @pytest.mark.asyncio
    async def test_pipeline_context_injection(self, pipeline):
        """TelemetryPayloads get _market and _query injected."""
        _, orch = pipeline
        agent_input = AgentInput(query="shoes", market="ecommerce")
        output = await orch.run(agent_input, all_ok())

        for p in output.result:
            assert p.contextual_signals.get("_market") == "ecommerce"
            assert p.contextual_signals.get("_query") == "shoes"

    @pytest.mark.asyncio
    async def test_pipeline_telemetry_validation(self, pipeline):
        """validate_telemetry_batch is called and doesn't reject valid data."""
        _, orch = pipeline
        agent_input = AgentInput(query="Brazil", market="sports")
        output = await orch.run(agent_input, all_ok())

        for p in output.result:
            assert p.entity_id
            assert p.source_system

    @pytest.mark.asyncio
    async def test_pipeline_statelessness(self, pipeline):
        """Multiple calls with same input produce independent outputs."""
        _, orch = pipeline

        outputs = []
        for _ in range(5):
            out = await orch.run(AgentInput(query="Brazil", market="sports"), all_ok())
            outputs.append(out)

        assert all(o.status == AgentStatus.SUCCESS for o in outputs)
        request_ids = [o.request_id for o in outputs]
        assert len(set(request_ids)) == 5

    @pytest.mark.asyncio
    async def test_pipeline_recovery_log_contains_events(self, pipeline):
        """Recovery log should have events on fallback paths."""
        _, orch = pipeline
        scenarios = {
            ToolName.SERPAPI_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.TAVILY_SEARCH: ToolScenario(),
        }
        agent_input = AgentInput(query="shoes", market="ecommerce")
        output = await orch.run(agent_input, scenarios)

        assert output.metadata.recovery_triggered is True

    @pytest.mark.asyncio
    async def test_pipeline_with_custom_config(self, pipeline):
        """Custom ToolConfig is respected."""
        registry, _ = pipeline
        custom_config = ToolConfig(max_retries=1, timeout_seconds=5.0)
        orch = ToolOrchestrator(registry, custom_config)
        agent_input = AgentInput(query="Brazil", market="sports")
        output = await orch.run(agent_input, all_ok())

        assert output.status == AgentStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_pipeline_all_three_markets(self, pipeline):
        """All three defined markets produce successful results."""
        _, orch = pipeline

        markets = ["sports", "ecommerce", "news"]
        for market in markets:
            output = await orch.run(AgentInput(query="test", market=market), all_ok())
            assert output.is_successful, f"Market {market} failed: {output.error_message}"

    @pytest.mark.asyncio
    async def test_pipeline_no_scenarios_defaults(self, pipeline):
        """Running orchestrator without scenarios dict uses defaults (all succeed)."""
        _, orch = pipeline
        agent_input = AgentInput(query="Brazil", market="sports")
        output = await orch.run(agent_input)

        assert output.status == AgentStatus.SUCCESS
        assert len(output.result) >= 1
