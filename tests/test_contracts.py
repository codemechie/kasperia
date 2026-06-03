"""Contract tests: TelemetryPayload, ToolResponse, AgentInput/Output, enums."""
from datetime import datetime
from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given
from hypothesis import strategies as st

from contracts.models import (
    TelemetryPayload,
    ToolResponse,
    AgentInput,
    AgentOutput,
    AgentStatus,
    AgentMetadata,
    RecoveryEvent,
    RecoveryStrategy,
    ToolName,
    ToolConfig,
)


# ============================================================================
# TelemetryPayload
# ============================================================================

class TestTelemetryPayload:
    def test_immutable(self, sample_payload_sports):
        with pytest.raises(FrozenInstanceError):
            sample_payload_sports.entity_id = "changed"

    def test_minimal_construction(self):
        p = TelemetryPayload(
            source_system=ToolName.API_FOOTBALL,
            timestamp=datetime.utcnow(),
            entity_id="test_123",
        )
        assert p.source_system == ToolName.API_FOOTBALL
        assert p.entity_id == "test_123"
        assert p.metrics == {}
        assert p.contextual_signals == {}
        assert p.status == "OK"
        assert p.confidence == 1.0
        assert p.latency_ms == 0.0
        assert p.raw_data is None

    def test_default_values(self, sample_payload_sports):
        assert sample_payload_sports.metrics["home_score"] == 2
        assert sample_payload_sports.metrics["away_score"] == 1
        assert sample_payload_sports.status == "OK"
        assert sample_payload_sports.confidence == 0.95

    def test_entity_id_uniqueness(self, sample_payload_sports, sample_payload_news):
        assert sample_payload_sports.entity_id != sample_payload_news.entity_id

    def test_tool_name_is_enum(self, sample_payload_sports):
        assert isinstance(sample_payload_sports.source_system, ToolName)
        assert sample_payload_sports.source_system == ToolName.API_FOOTBALL

    @given(
        entity_id=st.text(min_size=1, max_size=50),
        confidence=st.floats(min_value=0.0, max_value=1.0),
        latency=st.floats(min_value=0.0, max_value=10000.0),
    )
    def test_property_based_construction(self, entity_id, confidence, latency):
        p = TelemetryPayload(
            source_system=ToolName.TAVILY_SEARCH,
            timestamp=datetime.utcnow(),
            entity_id=entity_id,
            confidence=confidence,
            latency_ms=latency,
        )
        assert p.source_system == ToolName.TAVILY_SEARCH
        assert p.entity_id == entity_id
        assert p.confidence == confidence
        assert p.latency_ms == latency


# ============================================================================
# ToolResponse
# ============================================================================

class TestToolResponse:
    def test_is_success(self, sample_tool_response):
        assert sample_tool_response.is_success() is True
        assert sample_tool_response.is_retryable() is False

    def test_is_retryable_timeout(self, sample_payload_sports):
        r = ToolResponse(
            tool_name=ToolName.API_FOOTBALL,
            status="timeout",
            data=[sample_payload_sports],
        )
        assert r.is_success() is False
        assert r.is_retryable() is True

    def test_is_retryable_rate_limited(self, sample_payload_sports):
        r = ToolResponse(
            tool_name=ToolName.API_FOOTBALL,
            status="rate_limited",
            data=[sample_payload_sports],
        )
        assert r.is_success() is False
        assert r.is_retryable() is True

    def test_is_retryable_error(self, sample_payload_sports):
        r = ToolResponse(
            tool_name=ToolName.API_FOOTBALL,
            status="error",
            data=[sample_payload_sports],
        )
        assert r.is_success() is False
        assert r.is_retryable() is False

    def test_immutable(self, sample_tool_response):
        with pytest.raises(FrozenInstanceError):
            sample_tool_response.status = "error"

    def test_empty_data_list(self):
        r = ToolResponse(tool_name=ToolName.API_FOOTBALL, status="success")
        assert r.data == []

    def test_fetched_at_defaults(self):
        before = datetime.utcnow()
        r = ToolResponse(tool_name=ToolName.API_FOOTBALL, status="success")
        after = datetime.utcnow()
        assert before <= r.fetched_at <= after


# ============================================================================
# AgentInput / AgentOutput
# ============================================================================

class TestAgentInput:
    def test_immutable(self, agent_input_sports):
        with pytest.raises(FrozenInstanceError):
            agent_input_sports.query = "changed"

    def test_request_id_generated(self, agent_input_sports):
        assert agent_input_sports.request_id is not None
        assert len(agent_input_sports.request_id) > 0

    def test_context_defaults_empty(self, agent_input_sports):
        assert agent_input_sports.context == {}

    def test_config_none_by_default(self, agent_input_sports):
        assert agent_input_sports.config is None

    def test_from_fixture(self, agent_input_sports):
        assert agent_input_sports.query == "Brazil"
        assert agent_input_sports.market == "sports"


class TestAgentOutput:
    def test_total_latency_ms(self):
        import datetime as dt
        start = dt.datetime.utcnow() - dt.timedelta(seconds=1)
        end = dt.datetime.utcnow()
        output = AgentOutput(
            request_id="test-123",
            agent_id="test_agent",
            status=AgentStatus.SUCCESS,
            started_at=start,
            completed_at=end,
        )
        assert output.total_latency_ms > 900
        assert output.total_latency_ms < 2000

    def test_is_successful_success(self):
        output = AgentOutput(
            request_id="test-123",
            agent_id="test_agent",
            status=AgentStatus.SUCCESS,
        )
        assert output.is_successful is True

    def test_is_successful_partial(self):
        output = AgentOutput(
            request_id="test-123",
            agent_id="test_agent",
            status=AgentStatus.PARTIAL_SUCCESS,
        )
        assert output.is_successful is True

    def test_is_successful_failed(self):
        output = AgentOutput(
            request_id="test-123",
            agent_id="test_agent",
            status=AgentStatus.FAILED,
        )
        assert output.is_successful is False

    def test_is_successful_pending(self):
        output = AgentOutput(
            request_id="test-123",
            agent_id="test_agent",
            status=AgentStatus.PENDING,
        )
        assert output.is_successful is False

    def test_immutable(self):
        output = AgentOutput(
            request_id="test-123",
            agent_id="test_agent",
            status=AgentStatus.SUCCESS,
        )
        with pytest.raises(FrozenInstanceError):
            output.status = AgentStatus.FAILED

    def test_error_message_optional(self):
        output = AgentOutput(
            request_id="test-123",
            agent_id="test_agent",
            status=AgentStatus.FAILED,
            error_message="Something went wrong",
        )
        assert output.error_message == "Something went wrong"


# ============================================================================
# Enums
# ============================================================================

class TestToolName:
    def test_values(self):
        assert ToolName.API_FOOTBALL.value == "api_football"
        assert ToolName.TAVILY_SEARCH.value == "tavily_search"
        assert ToolName.SERPAPI_SEARCH.value == "serpapi_search"
        assert ToolName.LOCAL_CACHE.value == "local_cache"

    def test_uniqueness(self):
        names = [e.value for e in ToolName]
        assert len(names) == len(set(names))


class TestRecoveryStrategy:
    def test_values(self):
        assert RecoveryStrategy.PRIMARY_SUCCESS.value == "primary_success"
        assert RecoveryStrategy.SWITCHED_TO_FALLBACK_1.value == "switched_to_fallback_1"
        assert RecoveryStrategy.SWITCHED_TO_FALLBACK_2.value == "switched_to_fallback_2"
        assert RecoveryStrategy.SWITCHED_TO_CACHE.value == "switched_to_cache"
        assert RecoveryStrategy.SYNTHESIS_REQUIRED.value == "synthesis_required"
        assert RecoveryStrategy.FAILED_ALL_TOOLS.value == "failed_all_tools"

    def test_uniqueness(self):
        names = [e.value for e in RecoveryStrategy]
        assert len(names) == len(set(names))


class TestAgentStatus:
    def test_values(self):
        assert AgentStatus.PENDING.value == "pending"
        assert AgentStatus.RUNNING.value == "running"
        assert AgentStatus.SUCCESS.value == "success"
        assert AgentStatus.PARTIAL_SUCCESS.value == "partial_success"
        assert AgentStatus.FAILED.value == "failed"

    def test_ordering(self):
        assert AgentStatus.SUCCESS != AgentStatus.FAILED


# ============================================================================
# RecoveryEvent
# ============================================================================

class TestRecoveryEvent:
    def test_immutable(self):
        event = RecoveryEvent(
            attempt_number=1,
            tool_attempted=ToolName.API_FOOTBALL,
            strategy=RecoveryStrategy.PRIMARY_SUCCESS,
            status="success",
        )
        with pytest.raises(FrozenInstanceError):
            event.attempt_number = 2

    def test_minimal_construction(self):
        event = RecoveryEvent(
            attempt_number=1,
            tool_attempted=ToolName.API_FOOTBALL,
            strategy=RecoveryStrategy.PRIMARY_SUCCESS,
            status="success",
        )
        assert event.reason is None
        assert event.latency_ms is None
        assert event.synthesized_from is None


# ============================================================================
# AgentMetadata
# ============================================================================

class TestAgentMetadata:
    def test_default_agent_id_generated(self):
        m = AgentMetadata()
        assert m.agent_id is not None
        assert len(m.agent_id) > 0

    def test_default_type(self):
        m = AgentMetadata()
        assert m.agent_type == "generic"

    def test_unique_ids(self):
        m1 = AgentMetadata()
        m2 = AgentMetadata()
        assert m1.agent_id != m2.agent_id

    def test_tools_lists_default_empty(self):
        m = AgentMetadata()
        assert m.tools_called == []
        assert m.tools_succeeded == []
        assert m.tools_failed == []
        assert m.recovery_triggered is False
        assert m.recovery_strategy is None


# ============================================================================
# ToolConfig
# ============================================================================

class TestToolConfig:
    def test_defaults(self):
        c = ToolConfig()
        assert c.max_retries == 3
        assert c.timeout_seconds == 30.0
        assert c.enable_fallbacks is True
        assert c.use_cache is True

    def test_immutable(self):
        c = ToolConfig()
        with pytest.raises(FrozenInstanceError):
            c.max_retries = 5

    def test_custom_values(self):
        c = ToolConfig(max_retries=1, timeout_seconds=10.0)
        assert c.max_retries == 1
        assert c.timeout_seconds == 10.0
