import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import uuid4

from contracts.models import (
    ToolName,
    ToolResponse,
    RecoveryEvent,
    RecoveryStrategy,
    AgentStatus,
    ToolConfig,
)
from tools.base import ToolScenarioMap
from tools.executor import ToolExecutor, ToolExecutionReport
from tools import MockToolRegistry

logger = logging.getLogger("RecoveryStateMachine")


class ExecutionState(str, Enum):
    IDLE = "idle"
    PRIMARY = "primary"
    FALLBACK = "fallback"
    RECOVERY = "recovery"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class AuditEvent:
    timestamp: datetime
    from_state: Optional[ExecutionState]
    to_state: ExecutionState
    event_type: str
    tool_name: Optional[str]
    attempt_number: int
    latency_ms: float
    status: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StateMachineResult:
    request_id: str
    query: str
    market: str
    final_state: ExecutionState
    final_status: AgentStatus
    strategy: RecoveryStrategy
    response: Optional[ToolResponse]
    audit_trail: List[AuditEvent]
    total_latency_ms: float
    primary_attempted: str
    fallbacks_attempted: List[str]


_VALID_TRANSITIONS: Dict[ExecutionState, List[ExecutionState]] = {
    ExecutionState.IDLE: [ExecutionState.PRIMARY],
    ExecutionState.PRIMARY: [ExecutionState.TERMINAL, ExecutionState.RECOVERY, ExecutionState.FALLBACK],
    ExecutionState.FALLBACK: [ExecutionState.TERMINAL, ExecutionState.RECOVERY],
    ExecutionState.RECOVERY: [ExecutionState.PRIMARY, ExecutionState.FALLBACK, ExecutionState.TERMINAL],
    ExecutionState.TERMINAL: [],
}


class RecoveryStateMachine:
    def __init__(
        self,
        registry: MockToolRegistry,
        config: Optional[ToolConfig] = None,
    ) -> None:
        self._registry = registry
        self._config = config or ToolConfig()
        self._executor = ToolExecutor(registry, config)
        self._reset()

    def _reset(self) -> None:
        self._state: ExecutionState = ExecutionState.IDLE
        self._audit_trail: List[AuditEvent] = []
        self._request_id: str = str(uuid4())
        self._query: str = ""
        self._market: str = ""
        self._primary_attempted: str = ""
        self._fallbacks_attempted: List[str] = []
        self._attempt_count: int = 0
        self._started_at: float = 0.0

    def _audit(
        self,
        event_type: str,
        message: str,
        tool_name: Optional[str] = None,
        status: str = "info",
        latency_ms: float = 0.0,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            from_state=self._state,
            to_state=self._state,
            event_type=event_type,
            tool_name=tool_name,
            attempt_number=self._attempt_count,
            latency_ms=latency_ms,
            status=status,
            message=message,
            details=details or {},
        )
        self._audit_trail.append(event)
        logger.info(
            f"[{self._request_id[:8]}] [{event_type}] {self._state.value} | {message}"
        )

    def _transition(
        self,
        to_state: ExecutionState,
        event_type: str,
        message: str,
        tool_name: Optional[str] = None,
        status: str = "info",
        latency_ms: float = 0.0,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        allowed = _VALID_TRANSITIONS.get(self._state, [])
        if to_state not in allowed and self._state != ExecutionState.IDLE:
            logger.warning(
                f"Invalid transition: {self._state.value} → {to_state.value} "
                f"(allowed from {self._state.value}: {[s.value for s in allowed]})"
            )
        from_state = self._state
        self._state = to_state
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            from_state=from_state,
            to_state=to_state,
            event_type=event_type,
            tool_name=tool_name,
            attempt_number=self._attempt_count,
            latency_ms=latency_ms,
            status=status,
            message=message,
            details=details or {},
        )
        self._audit_trail.append(event)
        logger.info(
            f"[{self._request_id[:8]}] {from_state.value} → {to_state.value} "
            f"| {event_type} | {message}"
        )

    async def execute(
        self,
        primary: ToolName,
        fallbacks: List[ToolName],
        query: str,
        market: str,
        scenarios: Optional[ToolScenarioMap] = None,
    ) -> StateMachineResult:
        self._reset()
        self._query = query
        self._market = market
        self._primary_attempted = primary.value
        self._fallbacks_attempted = [f.value for f in fallbacks]
        self._started_at = time.monotonic()

        # --- IDLE → PRIMARY ---
        self._transition(
            ExecutionState.PRIMARY,
            "phase_start",
            f"Starting primary tool: {primary.value}",
            tool_name=primary.value,
        )

        # --- PHASE 1: PRIMARY with retries ---
        max_retries = self._config.max_retries
        primary_report: Optional[ToolExecutionReport] = None
        resolving_tool_index = 0

        while self._attempt_count < max_retries:
            self._attempt_count += 1
            self._audit(
                "tool_attempt",
                f"Primary attempt {self._attempt_count}/{max_retries}",
                tool_name=primary.value,
                status="running",
            )

            report = await self._executor.execute(
                primary=primary,
                fallbacks=[],
                query=query,
                market=market,
                scenarios=scenarios,
            )

            if report.overall_status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL_SUCCESS):
                latency = (time.monotonic() - self._started_at) * 1000
                self._transition(
                    ExecutionState.TERMINAL,
                    "phase_complete",
                    f"Primary succeeded on attempt {self._attempt_count}",
                    tool_name=primary.value,
                    status="success",
                    latency_ms=latency,
                    details={"strategy": report.strategy.value, "total_latency_ms": report.total_latency_ms},
                )
                return self._build_result(report, resolving_tool_index)

            primary_report = report
            self._audit(
                "tool_failed",
                f"Primary attempt {self._attempt_count} failed: {report.strategy.value}",
                tool_name=primary.value,
                status="failed",
                latency_ms=report.total_latency_ms,
                details={"strategy": report.strategy.value, "error_count": len(report.attempts)},
            )

            if self._attempt_count < max_retries:
                self._transition(
                    ExecutionState.RECOVERY,
                    "recovery_retry",
                    f"Retrying primary ({self._attempt_count + 1}/{max_retries})",
                    tool_name=primary.value,
                    status="recovery",
                )

        # --- PRIMARY EXHAUSTED → FALLBACK or TERMINAL ---
        if not fallbacks:
            self._transition(
                ExecutionState.TERMINAL,
                "phase_complete",
                "Primary exhausted, no fallbacks configured",
                status="failed",
            )
            assert primary_report is not None
            return self._build_result(primary_report, resolving_tool_index)

        resolving_tool_index = 1
        self._transition(
            ExecutionState.FALLBACK,
            "phase_start",
            f"Primary exhausted, entering fallback chain: {[f.value for f in fallbacks]}",
            tool_name=fallbacks[0].value,
            status="info",
            details={"fallbacks": [f.value for f in fallbacks]},
        )

        # --- PHASE 2: FALLBACK CHAIN ---
        fallback_report = await self._executor.execute(
            primary=fallbacks[0],
            fallbacks=fallbacks[1:],
            query=query,
            market=market,
            scenarios=scenarios,
        )

        if fallback_report.overall_status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL_SUCCESS):
            latency = (time.monotonic() - self._started_at) * 1000
            self._transition(
                ExecutionState.TERMINAL,
                "phase_complete",
                f"Fallback succeeded via {fallback_report.strategy.value}",
                tool_name=fallback_report.response.tool_name.value if fallback_report.response else None,
                status="success",
                latency_ms=latency,
                details={"strategy": fallback_report.strategy.value},
            )
            return self._build_result(fallback_report, resolving_tool_index)

        self._transition(
            ExecutionState.TERMINAL,
            "phase_complete",
            "All strategies exhausted",
            status="failed",
        )
        return self._build_result(fallback_report, resolving_tool_index)

    _STRATEGY_OFFSET = {
        RecoveryStrategy.PRIMARY_SUCCESS: 0,
        RecoveryStrategy.SWITCHED_TO_FALLBACK_1: 1,
        RecoveryStrategy.SWITCHED_TO_FALLBACK_2: 2,
        RecoveryStrategy.SWITCHED_TO_CACHE: 3,
    }

    _INDEX_TO_STRATEGY = [
        RecoveryStrategy.PRIMARY_SUCCESS,
        RecoveryStrategy.SWITCHED_TO_FALLBACK_1,
        RecoveryStrategy.SWITCHED_TO_FALLBACK_2,
        RecoveryStrategy.SWITCHED_TO_CACHE,
        RecoveryStrategy.SYNTHESIS_REQUIRED,
    ]

    def _overall_strategy(self, report: ToolExecutionReport, resolving_tool_index: int) -> RecoveryStrategy:
        if report.overall_status == AgentStatus.FAILED:
            return RecoveryStrategy.FAILED_ALL_TOOLS
        offset = self._STRATEGY_OFFSET.get(report.strategy, 0)
        overall_index = resolving_tool_index + offset
        if overall_index < len(self._INDEX_TO_STRATEGY):
            return self._INDEX_TO_STRATEGY[overall_index]
        return RecoveryStrategy.SYNTHESIS_REQUIRED

    def _build_result(self, report: ToolExecutionReport, resolving_tool_index: int = 0) -> StateMachineResult:
        total_latency = (time.monotonic() - self._started_at) * 1000
        overall = self._overall_strategy(report, resolving_tool_index)

        self._audit_trail.append(AuditEvent(
            timestamp=datetime.utcnow(),
            from_state=None,
            to_state=ExecutionState.TERMINAL,
            event_type="summary",
            tool_name=None,
            attempt_number=self._attempt_count,
            latency_ms=total_latency,
            status=report.overall_status.value,
            message=(
                f"Final: {report.overall_status.value} via {overall.value} "
                f"in {total_latency:.0f}ms"
            ),
            details={
                "total_latency_ms": total_latency,
                "executor_latency_ms": report.total_latency_ms,
                "strategy": overall.value,
                "executor_strategy": report.strategy.value,
                "resolving_tool_index": resolving_tool_index,
                "attempts": report.attempts,
                "recovery_log": [
                    {
                        "tool": e.tool_attempted.value,
                        "strategy": e.strategy.value,
                        "status": e.status,
                        "latency_ms": e.latency_ms,
                        "reason": e.reason,
                    }
                    for e in report.recovery_log
                ],
            },
        ))

        return StateMachineResult(
            request_id=self._request_id,
            query=self._query,
            market=self._market,
            final_state=ExecutionState.TERMINAL,
            final_status=report.overall_status,
            strategy=overall,
            response=report.response,
            audit_trail=list(self._audit_trail),
            total_latency_ms=total_latency,
            primary_attempted=self._primary_attempted,
            fallbacks_attempted=self._fallbacks_attempted,
        )
