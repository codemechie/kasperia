import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any

from contracts.models import (
    AgentInput,
    AgentOutput,
    AgentStatus,
    AgentMetadata,
    ToolName,
    RecoveryStrategy,
)
from contracts.validators import validate_telemetry_batch
from tools import MockToolRegistry
from tools.base import ToolScenarioMap
from tools.executor import ToolConfig
from orchestrator.state_machine import RecoveryStateMachine

logger = logging.getLogger("ToolOrchestrator")


@dataclass
class ToolChain:
    primary: ToolName
    fallbacks: List[ToolName]


_MARKET_TOOLS: Dict[str, ToolChain] = {
    "sports": ToolChain(
        primary=ToolName.API_FOOTBALL,
        fallbacks=[ToolName.TAVILY_SEARCH, ToolName.SERPAPI_SEARCH, ToolName.LOCAL_CACHE],
    ),
    "ecommerce": ToolChain(
        primary=ToolName.SERPAPI_SEARCH,
        fallbacks=[ToolName.TAVILY_SEARCH, ToolName.LOCAL_CACHE],
    ),
    "news": ToolChain(
        primary=ToolName.TAVILY_SEARCH,
        fallbacks=[ToolName.SERPAPI_SEARCH, ToolName.LOCAL_CACHE],
    ),
    "general": ToolChain(
        primary=ToolName.TAVILY_SEARCH,
        fallbacks=[ToolName.SERPAPI_SEARCH, ToolName.LOCAL_CACHE],
    ),
}

_DEFAULT_CHAIN = ToolChain(
    primary=ToolName.TAVILY_SEARCH,
    fallbacks=[ToolName.SERPAPI_SEARCH, ToolName.LOCAL_CACHE],
)


class ToolOrchestrator:
    def __init__(
        self,
        registry: MockToolRegistry,
        config: Optional[ToolConfig] = None,
    ) -> None:
        self._config = config or ToolConfig()
        self._state_machine = RecoveryStateMachine(registry, self._config)

    async def run(
        self,
        agent_input: AgentInput,
        scenarios: Optional[ToolScenarioMap] = None,
    ) -> AgentOutput:
        started_at = datetime.utcnow()
        logger.info(
            f"[{agent_input.request_id[:8]}] Orchestrating: "
            f"query={agent_input.query!r} market={agent_input.market!r}"
        )

        try:
            chain = self._select_chain(agent_input.market)
            logger.info(
                f"[{agent_input.request_id[:8]}] Tool chain: "
                f"primary={chain.primary.value} fallbacks={[f.value for f in chain.fallbacks]}"
            )

            sm_result = await self._state_machine.execute(
                primary=chain.primary,
                fallbacks=chain.fallbacks,
                query=agent_input.query,
                market=agent_input.market,
                scenarios=scenarios,
            )

            if sm_result.response and sm_result.response.data:
                telemetry = list(sm_result.response.data)
                try:
                    validate_telemetry_batch(telemetry)
                except ValueError as e:
                    logger.error(f"Validation failed: {e}")
                    return self._build_output(
                        agent_input, started_at,
                        status=AgentStatus.FAILED,
                        error_message=f"Output validation failed: {e}",
                        recovery_log=sm_result.audit_trail,
                    )

                # Mark each payload with the orchestrator market context
                for p in telemetry:
                    signals = dict(p.contextual_signals)
                    signals["_market"] = agent_input.market
                    signals["_query"] = agent_input.query

                status = (
                    AgentStatus.SUCCESS
                    if sm_result.strategy == RecoveryStrategy.PRIMARY_SUCCESS
                    else AgentStatus.PARTIAL_SUCCESS
                )

                return self._build_output(
                    agent_input, started_at,
                    status=status,
                    result=telemetry,
                    strategy=sm_result.strategy,
                    recovery_log=sm_result.audit_trail,
                    tools_called=sm_result.fallbacks_attempted + [sm_result.primary_attempted],
                    tools_succeeded=[p.source_system.value for p in telemetry],
                )

            return self._build_output(
                agent_input, started_at,
                status=AgentStatus.FAILED,
                error_message=f"No data returned. Strategy: {sm_result.strategy.value}",
                strategy=sm_result.strategy,
                recovery_log=sm_result.audit_trail,
                tools_called=sm_result.fallbacks_attempted + [sm_result.primary_attempted],
            )

        except Exception as e:
            logger.exception(f"Orchestrator failed for {agent_input.request_id[:8]}")
            return self._build_output(
                agent_input, started_at,
                status=AgentStatus.FAILED,
                error_message=str(e),
            )

    def _select_chain(self, market: str) -> ToolChain:
        return _MARKET_TOOLS.get(market.lower().strip(), _DEFAULT_CHAIN)

    def _build_output(
        self,
        agent_input: AgentInput,
        started_at: datetime,
        status: AgentStatus,
        result: Optional[List] = None,
        error_message: Optional[str] = None,
        strategy: Optional[RecoveryStrategy] = None,
        recovery_log: Optional[List] = None,
        tools_called: Optional[List[str]] = None,
        tools_succeeded: Optional[List[str]] = None,
    ) -> AgentOutput:
        completed_at = datetime.utcnow()
        delta = (completed_at - started_at).total_seconds() * 1000

        audit_events = []
        if recovery_log:
            for e in recovery_log:
                audit_events.append({
                    "event_type": getattr(e, "event_type", "event"),
                    "state": getattr(e, "to_state", getattr(e, "from_state", None)),
                    "message": getattr(e, "message", str(e)),
                })

        return AgentOutput(
            request_id=agent_input.request_id,
            agent_id="tool_orchestrator",
            status=status,
            result=list(result) if result else [],
            recovery_log=[],
            metadata=AgentMetadata(
                agent_id=f"orch_{agent_input.request_id[:8]}",
                agent_type="orchestrator",
                started_at=started_at,
                completed_at=completed_at,
                total_latency_ms=delta,
                tools_called=[ToolName(t) for t in (tools_called or [])],
                tools_succeeded=[ToolName(t) for t in (tools_succeeded or [])],
                tools_failed=[],
                recovery_triggered=(status == AgentStatus.PARTIAL_SUCCESS),
                recovery_strategy=strategy,
                reasoning_trace=(
                    f"Market={agent_input.market}, "
                    f"Strategy={strategy.value if strategy else 'none'}, "
                    f"Audit: {' | '.join(e['message'] for e in audit_events[-3:])}"
                ) if audit_events else None,
            ),
            error_message=error_message,
            error_details={
                "market": agent_input.market,
                "query": agent_input.query,
                "strategy": strategy.value if strategy else None,
                "total_latency_ms": delta,
            } if error_message else None,
            started_at=started_at,
            completed_at=completed_at,
        )
