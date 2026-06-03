"""Unit tests for mock tool implementations under every ToolScenario."""
import pytest
from datetime import datetime

from contracts.models import ToolName, ToolResponse
from tools import (
    ApiFootballMock,
    TavilyMock,
    SerpApiMock,
    CacheMock,
    MockToolRegistry,
)
from tools.base import ToolScenario


# ============================================================================
# ApiFootballMock
# ============================================================================

class TestApiFootballMock:
    @pytest.fixture
    def tool(self):
        return ApiFootballMock()

    @pytest.mark.asyncio
    async def test_success(self, tool):
        response = await tool.execute("Brazil", "sports")
        assert isinstance(response, ToolResponse)
        assert response.status == "success"
        assert len(response.data) >= 1
        p = response.data[0]
        assert p.source_system == ToolName.API_FOOTBALL
        assert "brazil" in p.entity_id or "france" in p.entity_id

    @pytest.mark.asyncio
    async def test_confidence(self, tool):
        response = await tool.execute("Brazil", "sports")
        assert response.confidence == 0.95
        assert response.data[0].confidence == 0.95

    @pytest.mark.asyncio
    async def test_entity_id_format(self, tool):
        response = await tool.execute("Brazil", "sports")
        p = response.data[0]
        assert p.entity_id.startswith("match_")
        parts = p.entity_id.split("_")
        assert len(parts) >= 4

    @pytest.mark.asyncio
    async def test_metrics_shape(self, tool):
        response = await tool.execute("Brazil", "sports")
        p = response.data[0]
        assert "home_score" in p.metrics
        assert "away_score" in p.metrics
        assert isinstance(p.metrics["home_score"], int)
        assert isinstance(p.metrics["away_score"], int)

    @pytest.mark.asyncio
    async def test_signals_shape(self, tool):
        response = await tool.execute("Brazil", "sports")
        p = response.data[0]
        assert "home_team" in p.contextual_signals
        assert "away_team" in p.contextual_signals
        assert "league" in p.contextual_signals
        assert "venue" in p.contextual_signals

    @pytest.mark.asyncio
    async def test_failure_mode_error(self, tool):
        scenario = ToolScenario(failure_mode="error", failure_probability=1.0)
        with pytest.raises(RuntimeError, match="Simulated tool error"):
            await tool.execute("Brazil", "sports", scenario)

    @pytest.mark.asyncio
    async def test_failure_mode_timeout(self, tool):
        scenario = ToolScenario(failure_mode="timeout", failure_probability=1.0)
        with pytest.raises(TimeoutError, match="Simulated tool timeout"):
            await tool.execute("Brazil", "sports", scenario)

    @pytest.mark.asyncio
    async def test_failure_mode_rate_limited(self, tool):
        scenario = ToolScenario(failure_mode="rate_limited", failure_probability=1.0)
        with pytest.raises(RuntimeError, match="Simulated rate limit"):
            await tool.execute("Brazil", "sports", scenario)

    @pytest.mark.asyncio
    async def test_force_status(self, tool):
        scenario = ToolScenario(force_status="error")
        with pytest.raises(RuntimeError, match="Simulated tool error"):
            await tool.execute("Brazil", "sports", scenario)

    @pytest.mark.asyncio
    async def test_probabilistic_failure(self, tool):
        scenario = ToolScenario(failure_mode="error", failure_probability=1.0)
        with pytest.raises(RuntimeError):
            await tool.execute("Brazil", "sports", scenario)

    @pytest.mark.asyncio
    async def test_zero_probability(self, tool):
        scenario = ToolScenario(failure_mode="error", failure_probability=0.0)
        response = await tool.execute("Brazil", "sports", scenario)
        assert response.status == "success"

    @pytest.mark.asyncio
    async def test_latency_scenario(self, tool):
        scenario = ToolScenario(latency_range=(0.01, 0.02))
        import time
        start = time.monotonic()
        await tool.execute("Brazil", "sports", scenario)
        elapsed = (time.monotonic() - start) * 1000
        assert elapsed >= 10

    @pytest.mark.asyncio
    async def test_tool_name_property(self, tool):
        assert tool.tool_name == ToolName.API_FOOTBALL

    @pytest.mark.asyncio
    async def test_query_matching(self, tool):
        response = await tool.execute("England", "sports")
        p = response.data[0]
        signals = p.contextual_signals
        assert "England" in signals.get("home_team", "") or "England" in signals.get("away_team", "")

    @pytest.mark.asyncio
    async def test_timestamp_set(self, tool):
        response = await tool.execute("Brazil", "sports")
        assert isinstance(response.fetched_at, datetime)
        assert response.data[0].timestamp is not None


# ============================================================================
# TavilyMock
# ============================================================================

class TestTavilyMock:
    @pytest.fixture
    def tool(self):
        return TavilyMock()

    @pytest.mark.asyncio
    async def test_success(self, tool):
        response = await tool.execute("Brazil", "news")
        assert response.status == "success"
        assert len(response.data) >= 1
        p = response.data[0]
        assert p.source_system == ToolName.TAVILY_SEARCH

    @pytest.mark.asyncio
    async def test_confidence(self, tool):
        response = await tool.execute("Brazil", "news")
        assert response.confidence == 0.75
        assert response.data[0].confidence == 0.75

    @pytest.mark.asyncio
    async def test_entity_id_format(self, tool):
        response = await tool.execute("Brazil", "news")
        p = response.data[0]
        assert p.entity_id.startswith("search_")

    @pytest.mark.asyncio
    async def test_signals_shape(self, tool):
        response = await tool.execute("Brazil", "news")
        p = response.data[0]
        assert "title" in p.contextual_signals
        assert "content" in p.contextual_signals
        assert "source_url" in p.contextual_signals
        assert "published_date" in p.contextual_signals

    @pytest.mark.asyncio
    async def test_metrics_shape(self, tool):
        response = await tool.execute("Brazil", "news")
        p = response.data[0]
        assert "num_results" in p.metrics

    @pytest.mark.asyncio
    async def test_failure_mode_error(self, tool):
        scenario = ToolScenario(failure_mode="error", failure_probability=1.0)
        with pytest.raises(RuntimeError, match="Simulated tool error"):
            await tool.execute("Brazil", "news", scenario)

    @pytest.mark.asyncio
    async def test_tool_name_property(self, tool):
        assert tool.tool_name == ToolName.TAVILY_SEARCH

    @pytest.mark.asyncio
    async def test_query_matching(self, tool):
        response = await tool.execute("Brazil", "news")
        p = response.data[0]
        assert "Brazil" in p.contextual_signals.get("title", "")


# ============================================================================
# SerpApiMock
# ============================================================================

class TestSerpApiMock:
    @pytest.fixture
    def tool(self):
        return SerpApiMock()

    @pytest.mark.asyncio
    async def test_success(self, tool):
        response = await tool.execute("shoes", "ecommerce")
        assert response.status == "success"
        assert len(response.data) >= 1
        p = response.data[0]
        assert p.source_system == ToolName.SERPAPI_SEARCH

    @pytest.mark.asyncio
    async def test_confidence(self, tool):
        response = await tool.execute("shoes", "ecommerce")
        assert response.confidence == 0.60
        assert response.data[0].confidence == 0.60

    @pytest.mark.asyncio
    async def test_entity_id_format(self, tool):
        response = await tool.execute("shoes", "ecommerce")
        p = response.data[0]
        assert p.entity_id.startswith("serpapi_")

    @pytest.mark.asyncio
    async def test_signals_shape(self, tool):
        response = await tool.execute("shoes", "ecommerce")
        p = response.data[0]
        assert "title" in p.contextual_signals
        assert "snippet" in p.contextual_signals
        assert "source_url" in p.contextual_signals
        assert "position" in p.contextual_signals

    @pytest.mark.asyncio
    async def test_failure_mode_error(self, tool):
        scenario = ToolScenario(failure_mode="error", failure_probability=1.0)
        with pytest.raises(RuntimeError, match="Simulated tool error"):
            await tool.execute("shoes", "ecommerce", scenario)

    @pytest.mark.asyncio
    async def test_failure_mode_timeout(self, tool):
        scenario = ToolScenario(failure_mode="timeout", failure_probability=1.0)
        with pytest.raises(TimeoutError, match="Simulated tool timeout"):
            await tool.execute("shoes", "ecommerce", scenario)

    @pytest.mark.asyncio
    async def test_force_status(self, tool):
        scenario = ToolScenario(force_status="error")
        with pytest.raises(RuntimeError):
            await tool.execute("shoes", "ecommerce", scenario)

    @pytest.mark.asyncio
    async def test_tool_name_property(self, tool):
        assert tool.tool_name == ToolName.SERPAPI_SEARCH


# ============================================================================
# CacheMock
# ============================================================================

class TestCacheMock:
    @pytest.fixture
    def tool(self):
        return CacheMock()

    @pytest.mark.asyncio
    async def test_cache_miss_returns_empty_data(self, tool):
        response = await tool.execute("Brazil", "sports")
        assert response.status == "success"
        assert response.data == []

    @pytest.mark.asyncio
    async def test_cache_hit(self, tool, sample_payload_sports):
        tool.seed("sports:brazil", sample_payload_sports)
        response = await tool.execute("Brazil", "sports")
        assert response.status == "success"
        assert len(response.data) == 1
        assert response.data[0].entity_id == sample_payload_sports.entity_id

    @pytest.mark.asyncio
    async def test_cache_hit_is_instant(self, tool, sample_payload_sports):
        tool.seed("sports:brazil", sample_payload_sports)
        response = await tool.execute("Brazil", "sports")
        assert response.latency_ms == 0.0

    @pytest.mark.asyncio
    async def test_cache_confidence(self, tool, sample_payload_sports):
        tool.seed("sports:brazil", sample_payload_sports)
        response = await tool.execute("Brazil", "sports")
        assert response.confidence == 0.50

    @pytest.mark.asyncio
    async def test_cache_miss_separate_key(self, tool, sample_payload_sports):
        tool.seed("news:technology", sample_payload_sports)
        response = await tool.execute("Brazil", "sports")
        assert response.data == []

    @pytest.mark.asyncio
    async def test_tool_name_property(self, tool):
        assert tool.tool_name == ToolName.LOCAL_CACHE

    @pytest.mark.asyncio
    async def test_seed_multiple_keys(self, tool, sample_payload_sports, sample_payload_news):
        tool.seed("sports:brazil", sample_payload_sports)
        tool.seed("news:tech", sample_payload_news)
        r1 = await tool.execute("Brazil", "sports")
        r2 = await tool.execute("tech", "news")
        assert len(r1.data) == 1
        assert len(r2.data) == 1
        assert r1.data[0].entity_id != r2.data[0].entity_id


# ============================================================================
# MockToolRegistry
# ============================================================================

class TestMockToolRegistry:
    def test_get_all_tools(self, registry):
        tools = registry.all()
        assert len(tools) == 4
        assert ToolName.API_FOOTBALL in tools
        assert ToolName.TAVILY_SEARCH in tools
        assert ToolName.SERPAPI_SEARCH in tools
        assert ToolName.LOCAL_CACHE in tools

    def test_get_returns_correct_type(self, registry):
        from tools.base import MockTool
        for name in ToolName:
            tool = registry.get(name)
            assert isinstance(tool, MockTool)

    def test_get_unknown_tool_raises(self, registry):
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    def test_register_new_tool(self, registry):
        class FakeTool:
            tool_name = ToolName.API_FOOTBALL
        tool = FakeTool()
        registry.register(tool)
        assert registry.get(ToolName.API_FOOTBALL) is tool

    def test_cache_property(self, registry):
        cache = registry.cache
        from tools import CacheMock
        assert isinstance(cache, CacheMock)

    def test_singleton_per_name(self, registry):
        t1 = registry.get(ToolName.API_FOOTBALL)
        t2 = registry.get(ToolName.API_FOOTBALL)
        assert t1 is t2
