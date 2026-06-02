import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from contracts.models import (
    ToolName,
    ToolResponse,
    RecoveryEvent,
    RecoveryStrategy,
    AgentStatus,
    ToolConfig,
)
from tools.base import MockTool, ToolScenario, ToolScenarioMap
from tools import MockToolRegistry

logger = logging.getLogger("ToolExecutor")


@dataclass
class ToolExecutionReport:
    response: Optional[ToolResponse]
    strategy: RecoveryStrategy
    overall_status: AgentStatus
    recovery_log: List[RecoveryEvent]
    total_latency_ms: float
    attempts: List[Dict[str, Any]] = field(default_factory=list)


_DEFAULT_SCENARIO = ToolScenario()


class ToolExecutor:
    def __init__(
        self,
        registry: MockToolRegistry,
        config: Optional[ToolConfig] = None,
    ) -> None:
        self._registry = registry
        self._config = config or ToolConfig()

    async def execute(
        self,
        primary: ToolName,
        fallbacks: List[ToolName],
        query: str,
        market: str,
        scenarios: Optional[ToolScenarioMap] = None,
    ) -> ToolExecutionReport:
        overall_start = time.monotonic()
        recovery_log: List[RecoveryEvent] = []
        attempts: List[Dict[str, Any]] = []
        final_response: Optional[ToolResponse] = None
        strategy = RecoveryStrategy.FAILED_ALL_TOOLS

        tool_chain = [primary] + fallbacks
        scenarios = scenarios or {}

        for idx, tool_name in enumerate(tool_chain):
            tool = self._registry.get(tool_name)
            scenario = scenarios.get(tool_name, _DEFAULT_SCENARIO)
            tool_start = time.monotonic()
            attempt_number = idx + 1

            try:
                response = await asyncio.wait_for(
                    tool.execute(query, market, scenario),
                    timeout=self._config.timeout_seconds,
                )

                if response.status == "success" and response.data:
                    latency_ms = (time.monotonic() - tool_start) * 1000
                    final_response = response
                    strategy = self._strategy_for(idx)
                    recovery_log.append(RecoveryEvent(
                        attempt_number=attempt_number,
                        tool_attempted=tool_name,
                        strategy=strategy,
                        status="success",
                        latency_ms=latency_ms,
                    ))
                    attempts.append({
                        "tool": tool_name.value,
                        "status": "success",
                        "latency_ms": latency_ms,
                        "attempt": attempt_number,
                    })
                    logger.info(
                        f"Tool {tool_name.value} succeeded "
                        f"(attempt {attempt_number}, strategy: {strategy.value})"
                    )
                    break

                latency_ms = (time.monotonic() - tool_start) * 1000
                attempts.append({
                    "tool": tool_name.value,
                    "status": response.status,
                    "latency_ms": latency_ms,
                    "attempt": attempt_number,
                    "data_count": len(response.data),
                })
                recovery_log.append(RecoveryEvent(
                    attempt_number=attempt_number,
                    tool_attempted=tool_name,
                    strategy=self._strategy_for(idx) if idx > 0 else RecoveryStrategy.PRIMARY_SUCCESS,
                    status="failed",
                    reason=f"Tool returned status={response.status} with {len(response.data)} payloads",
                    latency_ms=latency_ms,
                ))

            except asyncio.TimeoutError:
                latency_ms = (time.monotonic() - tool_start) * 1000
                attempts.append({
                    "tool": tool_name.value,
                    "status": "timeout",
                    "latency_ms": latency_ms,
                    "attempt": attempt_number,
                })
                recovery_log.append(RecoveryEvent(
                    attempt_number=attempt_number,
                    tool_attempted=tool_name,
                    strategy=self._strategy_for(idx) if idx > 0 else RecoveryStrategy.PRIMARY_SUCCESS,
                    status="failed",
                    reason=f"Timed out after {self._config.timeout_seconds}s",
                    latency_ms=latency_ms,
                ))

            except Exception as e:
                latency_ms = (time.monotonic() - tool_start) * 1000
                attempts.append({
                    "tool": tool_name.value,
                    "status": "error",
                    "latency_ms": latency_ms,
                    "attempt": attempt_number,
                    "error": str(e),
                })
                recovery_log.append(RecoveryEvent(
                    attempt_number=attempt_number,
                    tool_attempted=tool_name,
                    strategy=self._strategy_for(idx) if idx > 0 else RecoveryStrategy.PRIMARY_SUCCESS,
                    status="failed",
                    reason=str(e),
                    latency_ms=latency_ms,
                ))

        total_latency_ms = (time.monotonic() - overall_start) * 1000

        if final_response:
            status = AgentStatus.SUCCESS if strategy == RecoveryStrategy.PRIMARY_SUCCESS else AgentStatus.PARTIAL_SUCCESS
        else:
            status = AgentStatus.FAILED
            strategy = RecoveryStrategy.FAILED_ALL_TOOLS
            recovery_log.append(RecoveryEvent(
                attempt_number=len(tool_chain),
                tool_attempted=tool_chain[-1],
                strategy=RecoveryStrategy.FAILED_ALL_TOOLS,
                status="failed",
                reason="All tools in chain exhausted",
            ))

        return ToolExecutionReport(
            response=final_response,
            strategy=strategy,
            overall_status=status,
            recovery_log=recovery_log,
            total_latency_ms=total_latency_ms,
            attempts=attempts,
        )

    def _strategy_for(self, idx: int) -> RecoveryStrategy:
        mapping = [
            RecoveryStrategy.PRIMARY_SUCCESS,
            RecoveryStrategy.SWITCHED_TO_FALLBACK_1,
            RecoveryStrategy.SWITCHED_TO_FALLBACK_2,
            RecoveryStrategy.SWITCHED_TO_CACHE,
        ]
        return mapping[idx] if idx < len(mapping) else RecoveryStrategy.SYNTHESIS_REQUIRED
