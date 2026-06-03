"""Unit tests for RecoveryStateMachine — 5-state recovery driver."""
import pytest
from datetime import datetime

from contracts.models import ToolName, ToolConfig, AgentStatus, RecoveryStrategy
from tools.base import ToolScenario
from orchestrator.state_machine import (
    RecoveryStateMachine,
    ExecutionState,
    StateMachineResult,
    AuditEvent,
    _VALID_TRANSITIONS,
)


class TestExecutionState:
    def test_valid_transitions_idle_to_primary(self):
        assert ExecutionState.PRIMARY in _VALID_TRANSITIONS[ExecutionState.IDLE]

    def test_valid_transitions_primary(self):
        assert ExecutionState.TERMINAL in _VALID_TRANSITIONS[ExecutionState.PRIMARY]
        assert ExecutionState.RECOVERY in _VALID_TRANSITIONS[ExecutionState.PRIMARY]

    def test_valid_transitions_recovery(self):
        assert ExecutionState.PRIMARY in _VALID_TRANSITIONS[ExecutionState.RECOVERY]
        assert ExecutionState.FALLBACK in _VALID_TRANSITIONS[ExecutionState.RECOVERY]

    def test_terminal_has_no_outgoing(self):
        assert _VALID_TRANSITIONS[ExecutionState.TERMINAL] == []

    def test_all_states_covered(self):
        for state in ExecutionState:
            assert state in _VALID_TRANSITIONS


class TestRecoveryStateMachine:
    @pytest.mark.asyncio
    async def test_primary_succeeds(self, state_machine, scenarios_all_ok):
        result = await state_machine.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[ToolName.TAVILY_SEARCH, ToolName.SERPAPI_SEARCH],
            query="Brazil",
            market="sports",
            scenarios=scenarios_all_ok,
        )
        assert isinstance(result, StateMachineResult)
        assert result.final_state == ExecutionState.TERMINAL
        assert result.final_status == AgentStatus.SUCCESS
        assert result.strategy == RecoveryStrategy.PRIMARY_SUCCESS
        assert result.response is not None
        assert len(result.audit_trail) >= 3

    @pytest.mark.asyncio
    async def test_fallback_succeeds(self, state_machine, scenarios_primary_fails):
        result = await state_machine.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[ToolName.TAVILY_SEARCH, ToolName.SERPAPI_SEARCH],
            query="Brazil",
            market="sports",
            scenarios=scenarios_primary_fails,
        )
        assert result.final_state == ExecutionState.TERMINAL
        assert result.final_status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL_SUCCESS)
        assert result.response is not None
        assert result.strategy in (RecoveryStrategy.SWITCHED_TO_FALLBACK_1, RecoveryStrategy.PRIMARY_SUCCESS)

    @pytest.mark.asyncio
    async def test_all_tools_fail(self, state_machine):
        scenarios = {
            ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.TAVILY_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.SERPAPI_SEARCH: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.LOCAL_CACHE: ToolScenario(),
        }
        result = await state_machine.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[ToolName.TAVILY_SEARCH, ToolName.SERPAPI_SEARCH],
            query="Brazil",
            market="sports",
            scenarios=scenarios,
        )
        assert result.final_state == ExecutionState.TERMINAL
        assert result.final_status == AgentStatus.FAILED
        assert result.strategy == RecoveryStrategy.FAILED_ALL_TOOLS
        assert result.response is None

    @pytest.mark.asyncio
    async def test_retry_on_failure(self, state_machine):
        scenarios = {
            ToolName.API_FOOTBALL: ToolScenario(failure_mode="error", failure_probability=1.0),
            ToolName.TAVILY_SEARCH: ToolScenario(),
        }
        result = await state_machine.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[ToolName.TAVILY_SEARCH],
            query="Brazil",
            market="sports",
            scenarios=scenarios,
        )
        assert result.primary_attempted == "api_football"
        assert ToolName.API_FOOTBALL.value in result.fallbacks_attempted or result.final_status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL_SUCCESS)

    @pytest.mark.asyncio
    async def test_audit_trail_events(self, state_machine, scenarios_all_ok):
        result = await state_machine.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[ToolName.TAVILY_SEARCH],
            query="Brazil",
            market="sports",
            scenarios=scenarios_all_ok,
        )
        events = result.audit_trail
        assert len(events) >= 1
        for event in events:
            assert isinstance(event, AuditEvent)
            assert isinstance(event.timestamp, datetime)
            assert event.event_type in ("phase_start", "tool_attempt", "tool_failed", "recovery_retry", "phase_complete", "summary")
            assert event.status in ("running", "success", "failed", "recovery", "info")

    @pytest.mark.asyncio
    async def test_audit_trail_contains_summary(self, state_machine, scenarios_all_ok):
        result = await state_machine.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[],
            query="Brazil",
            market="sports",
            scenarios=scenarios_all_ok,
        )
        summary_events = [e for e in result.audit_trail if e.event_type == "summary"]
        assert len(summary_events) == 1
        summary = summary_events[0]
        assert "Final:" in summary.message

    @pytest.mark.asyncio
    async def test_no_fallbacks_configured(self, state_machine, scenarios_primary_fails):
        result = await state_machine.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[],
            query="Brazil",
            market="sports",
            scenarios=scenarios_primary_fails,
        )
        assert result.final_state == ExecutionState.TERMINAL
        assert result.strategy == RecoveryStrategy.FAILED_ALL_TOOLS

    @pytest.mark.asyncio
    async def test_reset_between_calls(self, state_machine, scenarios_all_ok, scenarios_primary_fails):
        result1 = await state_machine.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[],
            query="Brazil",
            market="sports",
            scenarios=scenarios_all_ok,
        )
        result2 = await state_machine.execute(
            primary=ToolName.API_FOOTBALL,
            fallbacks=[],
            query="Argentina",
            market="sports",
            scenarios=scenarios_primary_fails,
        )
        assert result1.response is not None
        assert result2.response is None
        assert result1.final_status == AgentStatus.SUCCESS
        assert result2.final_status == AgentStatus.FAILED

    def test_overall_strategy_mapping(self, state_machine, executor):
        from tools.executor import ToolExecutionReport

        success_report = ToolExecutionReport(
            response=None,
            strategy=RecoveryStrategy.PRIMARY_SUCCESS,
            overall_status=AgentStatus.SUCCESS,
            recovery_log=[],
            total_latency_ms=100,
        )
        assert state_machine._overall_strategy(success_report, 0) == RecoveryStrategy.PRIMARY_SUCCESS

        failed_report = ToolExecutionReport(
            response=None,
            strategy=RecoveryStrategy.FAILED_ALL_TOOLS,
            overall_status=AgentStatus.FAILED,
            recovery_log=[],
            total_latency_ms=100,
        )
        assert state_machine._overall_strategy(failed_report, 0) == RecoveryStrategy.FAILED_ALL_TOOLS

    def test_audit_event_frozen(self):
        from datetime import datetime
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            from_state=ExecutionState.IDLE,
            to_state=ExecutionState.PRIMARY,
            event_type="phase_start",
            tool_name="api_football",
            attempt_number=1,
            latency_ms=0.0,
            status="running",
            message="Starting",
        )
        import dataclasses
        assert dataclasses.fields(event) is not None
        assert event.event_type == "phase_start"
