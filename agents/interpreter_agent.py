"""
Interpreter Agent - Maps raw tool output to generic TelemetryPayload

This agent is the hardest part. It uses an LLM to understand ANY tool output
and map it to our unified schema, enabling the Strategy Swarm to reason generically.

Flow:
  Raw JSON/Text from tool → Interpreter Agent → TelemetryPayload
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import json
import logging

from contracts.models import (
    TelemetryPayload,
    ToolName,
    AgentInput,
    AgentOutput,
    AgentStatus,
    AgentMetadata,
    RecoveryEvent,
    RecoveryStrategy,
)
from contracts.validators import validate_telemetry_batch

logger = logging.getLogger("InterpreterAgent")


@dataclass
class RawToolOutput:
    """Raw output from a tool before interpretation."""
    tool_name: ToolName
    raw_data: Any  # JSON, text, dict, whatever
    latency_ms: float
    fetched_at: datetime


class InterpreterAgent:
    """
    Stateless function that maps raw tool output to TelemetryPayload.
    
    The hardest part of the resilient pipeline. Uses LLM to understand
    ANY tool output and extract:
    - entity_id (what's being described?)
    - metrics (numeric values)
    - contextual_signals (text/metadata)
    - status (OK, WARNING, CRITICAL?)
    """
    
    @staticmethod
    async def interpret(agent_input: AgentInput) -> AgentOutput:
        """
        Interpret raw tool output into generic TelemetryPayload objects.
        
        Input context should contain:
        - raw_outputs: List[RawToolOutput] from various tools
        
        Output result: List[TelemetryPayload]
        """
        started_at = datetime.utcnow()
        recovery_log = []
        
        try:
            raw_outputs = agent_input.context.get("raw_outputs", [])
            if not raw_outputs:
                return AgentOutput(
                    request_id=agent_input.request_id,
                    agent_id="interpreter_agent",
                    status=AgentStatus.FAILED,
                    result=[],
                    error_message="No raw_outputs provided in context",
                    metadata=AgentMetadata(
                        agent_type="interpreter",
                        recovery_triggered=False,
                    ),
                    completed_at=datetime.utcnow(),
                )
            
            # Attempt to interpret each raw output
            telemetry_payloads = []
            for raw_output in raw_outputs:
                try:
                    payload = await InterpreterAgent._interpret_single(raw_output)
                    telemetry_payloads.append(payload)
                except Exception as e:
                    logger.warning(f"Failed to interpret {raw_output.tool_name}: {e}")
                    recovery_log.append(RecoveryEvent(
                        attempt_number=1,
                        tool_attempted=raw_output.tool_name,
                        strategy=RecoveryStrategy.SYNTHESIS_REQUIRED,
                        status="failed",
                        reason=str(e),
                    ))
            
            if not telemetry_payloads:
                return AgentOutput(
                    request_id=agent_input.request_id,
                    agent_id="interpreter_agent",
                    status=AgentStatus.FAILED,
                    result=[],
                    error_message="Could not interpret any tool outputs",
                    recovery_log=recovery_log,
                    metadata=AgentMetadata(
                        agent_type="interpreter",
                        recovery_triggered=True,
                        recovery_strategy=RecoveryStrategy.FAILED_ALL_TOOLS,
                    ),
                    completed_at=datetime.utcnow(),
                )
            
            # Validate all payloads
            try:
                validate_telemetry_batch(telemetry_payloads)
            except Exception as e:
                logger.error(f"Validation failed: {e}")
                return AgentOutput(
                    request_id=agent_input.request_id,
                    agent_id="interpreter_agent",
                    status=AgentStatus.FAILED,
                    result=[],
                    error_message=f"Validation failed: {str(e)}",
                    recovery_log=recovery_log,
                    metadata=AgentMetadata(agent_type="interpreter"),
                    completed_at=datetime.utcnow(),
                )
            
            status = AgentStatus.SUCCESS if len(telemetry_payloads) == len(raw_outputs) else AgentStatus.PARTIAL_SUCCESS
            
            return AgentOutput(
                request_id=agent_input.request_id,
                agent_id="interpreter_agent",
                status=status,
                result=telemetry_payloads,
                recovery_log=recovery_log,
                metadata=AgentMetadata(
                    agent_type="interpreter",
                    tools_called=[o.tool_name for o in raw_outputs],
                    tools_succeeded=[o.tool_name for o in raw_outputs[:len(telemetry_payloads)]],
                    total_latency_ms=sum(o.latency_ms for o in raw_outputs),
                    recovery_triggered=len(recovery_log) > 0,
                ),
                completed_at=datetime.utcnow(),
            )
        
        except Exception as e:
            logger.exception("Interpreter agent failed")
            return AgentOutput(
                request_id=agent_input.request_id,
                agent_id="interpreter_agent",
                status=AgentStatus.FAILED,
                result=[],
                error_message=str(e),
                metadata=AgentMetadata(agent_type="interpreter"),
                completed_at=datetime.utcnow(),
            )
    
    @staticmethod
    async def _interpret_single(raw_output: RawToolOutput) -> TelemetryPayload:
        """
        Interpret a single raw tool output into TelemetryPayload.
        
        This is where the magic happens. Different tools have different formats:
        - API-Football: JSON with match, score, status
        - Tavily: JSON with articles, content, links
        - SerpApi: JSON with search results
        
        We extract the essence into a generic schema.
        """
        
        if raw_output.tool_name == ToolName.API_FOOTBALL:
            return InterpreterAgent._interpret_api_football(raw_output)
        
        elif raw_output.tool_name == ToolName.TAVILY_SEARCH:
            return InterpreterAgent._interpret_tavily(raw_output)
        
        elif raw_output.tool_name == ToolName.SERPAPI_SEARCH:
            return InterpreterAgent._interpret_serpapi(raw_output)
        
        elif raw_output.tool_name == ToolName.LOCAL_CACHE:
            return InterpreterAgent._interpret_cache(raw_output)
        
        else:
            raise ValueError(f"Unknown tool: {raw_output.tool_name}")
    
    @staticmethod
    def _interpret_api_football(raw_output: RawToolOutput) -> TelemetryPayload:
        """
        Map API-Football output to TelemetryPayload.
        
        Example raw_data:
        {
          "match_id": "12345",
          "home": {"name": "Brazil"},
          "away": {"name": "France"},
          "goals": {"home": 2, "away": 1},
          "status": "LIVE",
          "league": "World Cup",
          "venue": "Stadium X"
        }
        """
        data = raw_output.raw_data
        
        match_id = str(data.get("match_id", "unknown"))
        home_team = data.get("home", {}).get("name", "Unknown")
        away_team = data.get("away", {}).get("name", "Unknown")
        
        entity_id = f"match_{home_team.lower()}_{away_team.lower()}_{match_id}"
        
        metrics = {
            "home_score": data.get("goals", {}).get("home"),
            "away_score": data.get("goals", {}).get("away"),
        }
        
        contextual_signals = {
            "status": data.get("status", "UNKNOWN"),
            "league": data.get("league"),
            "venue": data.get("venue"),
            "home_team": home_team,
            "away_team": away_team,
        }
        
        status = "OK" if data.get("status") == "LIVE" else (
            "WARNING" if data.get("status") in ["DELAYED", "PAUSED"] else "OK"
        )
        
        return TelemetryPayload(
            source_system=ToolName.API_FOOTBALL,
            timestamp=raw_output.fetched_at,
            entity_id=entity_id,
            metrics=metrics,
            contextual_signals=contextual_signals,
            status=status,
            confidence=0.95,  # API-Football is high confidence
            latency_ms=raw_output.latency_ms,
            raw_data=data,
        )
    
    @staticmethod
    def _interpret_tavily(raw_output: RawToolOutput) -> TelemetryPayload:
        """
        Map Tavily Search output to TelemetryPayload.
        
        Example raw_data:
        {
          "results": [
            {
              "title": "Brazil beats France 2-1",
              "content": "In an exciting match...",
              "url": "https://...",
              "published_date": "2026-06-01"
            }
          ]
        }
        """
        data = raw_output.raw_data
        
        # Extract first result as primary entity
        results = data.get("results", [])
        if not results:
            raise ValueError("Tavily response has no results")
        
        first_result = results[0]
        title = first_result.get("title", "Unknown")
        content = first_result.get("content", "")
        url = first_result.get("url", "")
        
        entity_id = f"search_{title[:30].replace(' ', '_').lower()}"
        
        metrics = {
            "num_results": len(results),
        }
        
        contextual_signals = {
            "title": title,
            "content": content[:500],  # Truncate
            "source_url": url,
            "published_date": first_result.get("published_date"),
        }
        
        return TelemetryPayload(
            source_system=ToolName.TAVILY_SEARCH,
            timestamp=raw_output.fetched_at,
            entity_id=entity_id,
            metrics=metrics,
            contextual_signals=contextual_signals,
            status="OK",
            confidence=0.75,  # Search results are medium confidence
            latency_ms=raw_output.latency_ms,
            raw_data=data,
        )
    
    @staticmethod
    def _interpret_serpapi(raw_output: RawToolOutput) -> TelemetryPayload:
        """
        Map SerpApi output to TelemetryPayload.
        
        Similar structure to Tavily.
        """
        data = raw_output.raw_data
        
        results = data.get("organic_results", [])
        if not results:
            raise ValueError("SerpApi response has no results")
        
        first_result = results[0]
        title = first_result.get("title", "Unknown")
        snippet = first_result.get("snippet", "")
        link = first_result.get("link", "")
        
        entity_id = f"serpapi_{title[:30].replace(' ', '_').lower()}"
        
        metrics = {
            "num_results": len(results),
        }
        
        contextual_signals = {
            "title": title,
            "snippet": snippet,
            "source_url": link,
            "position": first_result.get("position", 1),
        }
        
        return TelemetryPayload(
            source_system=ToolName.SERPAPI_SEARCH,
            timestamp=raw_output.fetched_at,
            entity_id=entity_id,
            metrics=metrics,
            contextual_signals=contextual_signals,
            status="OK",
            confidence=0.60,  # SerpApi is fallback, lower confidence
            latency_ms=raw_output.latency_ms,
            raw_data=data,
        )
    
    @staticmethod
    def _interpret_cache(raw_output: RawToolOutput) -> TelemetryPayload:
        """Map cached data to TelemetryPayload."""
        data = raw_output.raw_data
        
        entity_id = data.get("entity_id", "cached_unknown")
        
        return TelemetryPayload(
            source_system=ToolName.LOCAL_CACHE,
            timestamp=raw_output.fetched_at,
            entity_id=entity_id,
            metrics=data.get("metrics", {}),
            contextual_signals=data.get("contextual_signals", {}),
            status=data.get("status", "OK"),
            confidence=0.50,  # Cache is lowest confidence
            latency_ms=0.0,  # Cache hits are instant
            raw_data=data,
        )
