"""
Data Contracts for Kasperia Resilient Multi-Tool Architecture

Core principle: Generic telemetry-based schema that unifies all tool outputs.
No domain-specific models. Agents reason over generic TelemetryPayload.

Raw Tool Output → Interpreter Agent → TelemetryPayload → Strategy Swarm → Result
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Literal
from uuid import uuid4


# ============================================================================
# ENUMS - Type-safe constants
# ============================================================================

class ToolName(str, Enum):
    """Identifiers for all available tools."""
    API_FOOTBALL = "api_football"
    TAVILY_SEARCH = "tavily_search"
    SERPAPI_SEARCH = "serpapi_search"
    LOCAL_CACHE = "local_cache"


class RecoveryStrategy(str, Enum):
    """Strategies executed during agent recovery."""
    PRIMARY_SUCCESS = "primary_success"
    SWITCHED_TO_FALLBACK_1 = "switched_to_fallback_1"
    SWITCHED_TO_FALLBACK_2 = "switched_to_fallback_2"
    SWITCHED_TO_CACHE = "switched_to_cache"
    SYNTHESIS_REQUIRED = "synthesis_required"
    FAILED_ALL_TOOLS = "failed_all_tools"


class AgentStatus(str, Enum):
    """Agent execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


# ============================================================================
# GENERIC TELEMETRY MODEL - The universal schema
# ============================================================================

@dataclass(frozen=True)
class TelemetryPayload:
    """
    Universal, generic schema for ANY data from ANY tool.
    
    This is the core of the system. All tools output gets mapped to this.
    Agents reason over TelemetryPayload without domain knowledge.
    """
    source_system: ToolName
    """Which tool provided this data (API_FOOTBALL, TAVILY_SEARCH, etc.)"""
    
    timestamp: datetime
    """When this data was fetched"""
    
    entity_id: str
    """The unique topic/identifier (e.g., 'match_bra_fra_2026', 'ticker_IBM', 'keyword_nike_shoes')"""
    
    metrics: Dict[str, Any] = field(default_factory=dict)
    """Numeric values changing over time (score, price, count, etc.)"""
    
    contextual_signals: Dict[str, Any] = field(default_factory=dict)
    """Textual metadata, news snippets, descriptions, logs"""
    
    status: Literal["OK", "WARNING", "CRITICAL", "UNKNOWN"] = "OK"
    """System state indicator"""
    
    # Traceability
    confidence: float = 1.0
    """How much to trust this data (0.0-1.0)"""
    
    latency_ms: float = 0.0
    """How long the tool took to provide this"""
    
    raw_data: Optional[Dict[str, Any]] = None
    """Optional: raw tool response for debugging"""


# ============================================================================
# TOOL RESPONSE CONTRACT
# ============================================================================

@dataclass(frozen=True)
class ToolResponse:
    """
    Standardized response envelope from any tool.
    
    All tools return this, containing a list of TelemetryPayload objects.
    """
    tool_name: ToolName
    status: Literal["success", "error", "timeout", "rate_limited"]
    data: List[TelemetryPayload] = field(default_factory=list)
    
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    
    latency_ms: float = 0.0
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    
    def is_success(self) -> bool:
        return self.status == "success"
    
    def is_retryable(self) -> bool:
        return self.status in ["timeout", "rate_limited"]


# ============================================================================
# RECOVERY & AUDITING - Observable self-healing
# ============================================================================

@dataclass(frozen=True)
class RecoveryEvent:
    """
    Immutable record of a recovery action during agent execution.
    """
    attempt_number: int
    tool_attempted: ToolName
    strategy: RecoveryStrategy
    status: Literal["success", "failed"]
    
    reason: Optional[str] = None
    latency_ms: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # For synthesis: which tools contributed
    synthesized_from: Optional[List[ToolName]] = None


@dataclass(frozen=True)
class AgentMetadata:
    """Metadata about agent execution for observability."""
    agent_id: str = field(default_factory=lambda: str(uuid4()))
    agent_type: str = "generic"  # "interpreter", "strategy_swarm", "orchestrator"
    
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_latency_ms: float = 0.0
    
    # Tool execution trace
    tools_called: List[ToolName] = field(default_factory=list)
    tools_succeeded: List[ToolName] = field(default_factory=list)
    tools_failed: List[ToolName] = field(default_factory=list)
    
    # Recovery details
    recovery_triggered: bool = False
    recovery_strategy: Optional[RecoveryStrategy] = None
    
    # Optional: reasoning trace
    reasoning_trace: Optional[str] = None


# ============================================================================
# AGENT CONTRACTS - Stateless function signatures
# ============================================================================

@dataclass(frozen=True)
class ToolConfig:
    """Configuration for tool execution."""
    max_retries: int = 3
    timeout_seconds: float = 30.0
    enable_fallbacks: bool = True
    fallback_timeout_seconds: float = 60.0
    use_cache: bool = True
    cache_ttl_seconds: int = 3600
    tool_settings: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentInput:
    """
    Input contract: What agents receive (immutable).
    
    Agents are pure functions: AgentInput → reasoning → AgentOutput
    """
    query: str
    """User's search query or entity identifier"""
    
    market: str
    """Domain/market context (e.g., 'sports', 'ecommerce', 'news')"""
    
    context: Dict[str, Any] = field(default_factory=dict)
    """Results from previous agents"""
    
    config: Optional[ToolConfig] = None
    
    request_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class AgentOutput:
    """
    Output contract: What agents return (immutable event).
    
    Contains list of TelemetryPayload (generic data) + recovery log.
    """
    request_id: str
    agent_id: str
    status: AgentStatus
    
    # The actual result - list of generic TelemetryPayload objects
    result: List[TelemetryPayload] = field(default_factory=list)
    
    # Recovery & auditing
    recovery_log: List[RecoveryEvent] = field(default_factory=list)
    metadata: AgentMetadata = field(default_factory=AgentMetadata)
    
    # Error context
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    
    # Execution timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def total_latency_ms(self) -> float:
        """Calculate total execution time."""
        delta = self.completed_at - self.started_at
        return delta.total_seconds() * 1000
    
    @property
    def is_successful(self) -> bool:
        """Quick success check."""
        return self.status in [AgentStatus.SUCCESS, AgentStatus.PARTIAL_SUCCESS]


# ============================================================================
# SYSTEM STATE - Orchestrator tracking
# ============================================================================

@dataclass(frozen=True)
class SystemState:
    """
    Immutable snapshot of system state.
    Used by orchestrator to track pipeline progress.
    """
    request_id: str
    query: str
    market: str
    overall_status: AgentStatus
    
    # Agent progress
    completed_agents: List[str] = field(default_factory=list)
    pending_agents: List[str] = field(default_factory=list)
    failed_agents: List[str] = field(default_factory=list)
    
    # Aggregated results - list of generic TelemetryPayload
    aggregated_result: List[TelemetryPayload] = field(default_factory=list)
    
    # Combined recovery log
    full_recovery_log: List[RecoveryEvent] = field(default_factory=list)
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
