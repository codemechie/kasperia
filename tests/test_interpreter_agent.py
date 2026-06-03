"""Unit tests for InterpreterAgent — raw tool output → TelemetryPayload."""
import pytest
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List

from contracts.models import AgentInput, AgentOutput, AgentStatus, ToolName
from agents.interpreter_agent import InterpreterAgent, RawToolOutput


def _make_agent_input(raw_outputs: List[RawToolOutput]) -> AgentInput:
    return AgentInput(
        query="test",
        market="general",
        context={"raw_outputs": raw_outputs},
    )


class TestInterpreterAgent:
    @pytest.mark.asyncio
    async def test_no_raw_outputs_returns_failed(self):
        agent_input = _make_agent_input([])
        output = await InterpreterAgent.interpret(agent_input)
        assert output.status == AgentStatus.FAILED
        assert output.error_message == "No raw_outputs provided in context"

    @pytest.mark.asyncio
    async def test_missing_raw_outputs_key(self):
        agent_input = AgentInput(query="test", market="general", context={})
        output = await InterpreterAgent.interpret(agent_input)
        assert output.status == AgentStatus.FAILED

    @pytest.mark.asyncio
    async def test_api_football_interpretation(self):
        raw = RawToolOutput(
            tool_name=ToolName.API_FOOTBALL,
            raw_data={
                "match_id": "12345",
                "home": {"name": "Brazil"},
                "away": {"name": "France"},
                "goals": {"home": 2, "away": 1},
                "status": "LIVE",
                "league": "World Cup",
                "venue": "Stadium X",
            },
            latency_ms=142.0,
            fetched_at=datetime.utcnow(),
        )
        output = await InterpreterAgent.interpret(_make_agent_input([raw]))
        assert output.status == AgentStatus.SUCCESS
        assert len(output.result) == 1
        p = output.result[0]
        assert p.source_system == ToolName.API_FOOTBALL
        assert "brazil" in p.entity_id
        assert "france" in p.entity_id
        assert p.metrics["home_score"] == 2
        assert p.metrics["away_score"] == 1
        assert p.contextual_signals["league"] == "World Cup"
        assert p.confidence == 0.95

    @pytest.mark.asyncio
    async def test_api_football_delayed_status(self):
        raw = RawToolOutput(
            tool_name=ToolName.API_FOOTBALL,
            raw_data={
                "match_id": "12345",
                "home": {"name": "Brazil"},
                "away": {"name": "France"},
                "goals": {"home": 0, "away": 0},
                "status": "DELAYED",
                "league": "World Cup",
                "venue": "Stadium X",
            },
            latency_ms=100.0,
            fetched_at=datetime.utcnow(),
        )
        output = await InterpreterAgent.interpret(_make_agent_input([raw]))
        p = output.result[0]
        assert p.status == "WARNING"

    @pytest.mark.asyncio
    async def test_tavily_interpretation(self):
        raw = RawToolOutput(
            tool_name=ToolName.TAVILY_SEARCH,
            raw_data={
                "results": [
                    {
                        "title": "Brazil beats France 2-1",
                        "content": "In an exciting match at Stadium X...",
                        "url": "https://sports-news.example.com/brazil-france",
                        "published_date": "2026-06-01",
                    }
                ]
            },
            latency_ms=200.0,
            fetched_at=datetime.utcnow(),
        )
        output = await InterpreterAgent.interpret(_make_agent_input([raw]))
        assert output.status == AgentStatus.SUCCESS
        assert len(output.result) == 1
        p = output.result[0]
        assert p.source_system == ToolName.TAVILY_SEARCH
        assert p.entity_id.startswith("search_")
        assert p.metrics["num_results"] == 1
        assert "Brazil" in p.contextual_signals["title"]
        assert p.confidence == 0.75

    @pytest.mark.asyncio
    async def test_tavily_empty_results_raises(self):
        raw = RawToolOutput(
            tool_name=ToolName.TAVILY_SEARCH,
            raw_data={"results": []},
            latency_ms=100.0,
            fetched_at=datetime.utcnow(),
        )
        output = await InterpreterAgent.interpret(_make_agent_input([raw]))
        assert output.status == AgentStatus.FAILED

    @pytest.mark.asyncio
    async def test_serpapi_interpretation(self):
        raw = RawToolOutput(
            tool_name=ToolName.SERPAPI_SEARCH,
            raw_data={
                "organic_results": [
                    {
                        "title": "Nike Air Max 270",
                        "snippet": "Buy Nike Air Max 270 at the best price",
                        "link": "https://shop.example.com/nike-air-max-270",
                        "position": 1,
                    }
                ]
            },
            latency_ms=180.0,
            fetched_at=datetime.utcnow(),
        )
        output = await InterpreterAgent.interpret(_make_agent_input([raw]))
        assert output.status == AgentStatus.SUCCESS
        assert len(output.result) == 1
        p = output.result[0]
        assert p.source_system == ToolName.SERPAPI_SEARCH
        assert p.entity_id.startswith("serpapi_")
        assert p.metrics["num_results"] == 1
        assert p.contextual_signals["position"] == 1
        assert p.confidence == 0.60

    @pytest.mark.asyncio
    async def test_serpapi_empty_results_raises(self):
        raw = RawToolOutput(
            tool_name=ToolName.SERPAPI_SEARCH,
            raw_data={"organic_results": []},
            latency_ms=100.0,
            fetched_at=datetime.utcnow(),
        )
        output = await InterpreterAgent.interpret(_make_agent_input([raw]))
        assert output.status == AgentStatus.FAILED

    @pytest.mark.asyncio
    async def test_cache_interpretation(self):
        cached_payload = {
            "entity_id": "cached_match_101",
            "metrics": {"home_score": 2},
            "contextual_signals": {"team": "Brazil"},
            "status": "OK",
        }
        raw = RawToolOutput(
            tool_name=ToolName.LOCAL_CACHE,
            raw_data=cached_payload,
            latency_ms=0.0,
            fetched_at=datetime.utcnow(),
        )
        output = await InterpreterAgent.interpret(_make_agent_input([raw]))
        assert output.status == AgentStatus.SUCCESS
        p = output.result[0]
        assert p.source_system == ToolName.LOCAL_CACHE
        assert p.entity_id == "cached_match_101"
        assert p.metrics["home_score"] == 2
        assert p.confidence == 0.50
        assert p.latency_ms == 0.0

    @pytest.mark.asyncio
    async def test_partial_success(self):
        good_raw = RawToolOutput(
            tool_name=ToolName.API_FOOTBALL,
            raw_data={
                "match_id": "1",
                "home": {"name": "Brazil"},
                "away": {"name": "France"},
                "goals": {"home": 2, "away": 1},
                "status": "LIVE",
                "league": "World Cup",
                "venue": "X",
            },
            latency_ms=100.0,
            fetched_at=datetime.utcnow(),
        )
        bad_raw = RawToolOutput(
            tool_name=ToolName.TAVILY_SEARCH,
            raw_data={"results": []},
            latency_ms=100.0,
            fetched_at=datetime.utcnow(),
        )
        output = await InterpreterAgent.interpret(_make_agent_input([good_raw, bad_raw]))
        assert output.status == AgentStatus.PARTIAL_SUCCESS
        assert len(output.result) == 1

    @pytest.mark.asyncio
    async def test_recovery_log_on_partial_failure(self):
        bad_raw = RawToolOutput(
            tool_name=ToolName.TAVILY_SEARCH,
            raw_data={"results": []},
            latency_ms=100.0,
            fetched_at=datetime.utcnow(),
        )
        output = await InterpreterAgent.interpret(_make_agent_input([bad_raw]))
        assert len(output.recovery_log) >= 1
        assert output.recovery_log[0].status == "failed"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_failed(self):
        raw = RawToolOutput(
            tool_name="unknown_tool",
            raw_data={"some": "data"},
            latency_ms=100.0,
            fetched_at=datetime.utcnow(),
        )
        output = await InterpreterAgent.interpret(_make_agent_input([raw]))
        assert output.status == AgentStatus.FAILED

    @pytest.mark.asyncio
    async def test_multiple_valid_tools(self):
        raw1 = RawToolOutput(
            tool_name=ToolName.API_FOOTBALL,
            raw_data={
                "match_id": "1",
                "home": {"name": "Brazil"},
                "away": {"name": "France"},
                "goals": {"home": 2, "away": 1},
                "status": "LIVE",
                "league": "World Cup",
                "venue": "X",
            },
            latency_ms=100.0,
            fetched_at=datetime.utcnow(),
        )
        raw2 = RawToolOutput(
            tool_name=ToolName.TAVILY_SEARCH,
            raw_data={
                "results": [{"title": "Test", "content": "Content", "url": "https://test.com", "published_date": "2026-01-01"}]
            },
            latency_ms=200.0,
            fetched_at=datetime.utcnow(),
        )
        output = await InterpreterAgent.interpret(_make_agent_input([raw1, raw2]))
        assert output.status == AgentStatus.SUCCESS
        assert len(output.result) == 2

    @pytest.mark.asyncio
    async def test_metadata_tools_called(self):
        raw = RawToolOutput(
            tool_name=ToolName.API_FOOTBALL,
            raw_data={
                "match_id": "1",
                "home": {"name": "Brazil"},
                "away": {"name": "France"},
                "goals": {"home": 2, "away": 1},
                "status": "LIVE",
                "league": "World Cup",
                "venue": "X",
            },
            latency_ms=100.0,
            fetched_at=datetime.utcnow(),
        )
        output = await InterpreterAgent.interpret(_make_agent_input([raw]))
        assert ToolName.API_FOOTBALL in output.metadata.tools_called
