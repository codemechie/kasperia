"""
Core data models for Kasperia agentic system.
All models are immutable (frozen=True) to support functional, event-driven architecture.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Literal
from uuid import uuid4


# ============================================================================
# Enums
# ============================================================================

class ToolName(str, Enum):
    """Supported tool identifiers."""
    API_FOOTBALL = "api_football"
    TAVILY_SEARCH = "tavily_search"
    SERPAPI_SEARCH = "serpapi_search"
    LOCAL_SCRAPER = "local_scraper"


class RecoveryStrategy(str, Enum):
    """Recovery strategies triggered during fallback."""
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


class ConfidenceLevel(str, Enum):
    """Data confidence scoring."""
    HIGH = "high"        # 0.85+
    MEDIUM = "medium"    # 0.60-0.84
    LOW = "low"          # <0.60


# ============================================================================
# Product & Search Result Models
# ============================================================================

@dataclass(frozen=True)
class Product:
    """Unified product schema across all data sources."""
    title: str
    price: float
    currency: str
    product_url: str
    store_name: str
    store_domain: str
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    in_stock: Optional[bool] = None
    image_url: Optional[str] = None
    
    # Metadata for traceability
    source_tool: ToolName = ToolName.LOCAL_SCRAPER
    confidence: float = 1.0  # 0.0 to 1.0
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Validate product data."""
        if self.price < 0:
            raise ValueError(f"Price cannot be negative: {self.price}")
        if not (0 <= self.confidence <= 1.0):
            raise ValueError(f"Confidence must be between 0 and 1: {self.confidence}")


@dataclass(frozen=True)
class SearchResult:
    """Unified search result schema (for news, sentiment, general queries)."""
    title: str
    content: str  # Main text content
    source_url: str
    source_domain: str
    published_at: Optional[datetime] = None
    relevance_score: float = 1.0  # 0.0 to 1.0
    
    # Metadata
    source_tool: ToolName = ToolName.TAVILY_SEARCH
    confidence: float = 1.0
    fetched_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================================
# Tool Response Contracts
# ============================================================================

@dataclass(frozen=True)
class ToolResponse:
    """
    Standardized response envelope from any tool.
    All tools must return this contract.
    """
    tool_name: ToolName
    status: Literal["success", "error", "timeout", "rate_limited"]
    data: Any  # Actual payload (List[Product], List[SearchResult], etc.)
    error_message: Optional[str] = None
    latency_ms: float = 0.0
    confidence: float = 1.0  # How much we trust this response
    metadata: Dict[str, Any] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    
    def is_success(self) -> bool:
        """Quick success check."""
        return self.status == "success"
    
    def is_retryable(self) -> bool:
        """Can this error be recovered via fallback?"""
        return self.status in ["timeout", "rate_limited"]


# ============================================================================
# Recovery & Event Models
# ============================================================================

@dataclass(frozen=True)
class RecoveryEvent:
    """
    Immutable record of a recovery action during agent execution.
    Used to build recovery_log for audit trail and debugging.
    """
    attempt_number: int
    tool_attempted: ToolName
    strategy: RecoveryStrategy
    status: Literal["success", "failed"]
    reason: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    latency_ms: Optional[float] = None
    
    # For synthesis events: which tools contributed data
    synthesized_from: Optional[List[ToolName]] = None


@dataclass(frozen=True)
class AgentMetadata:
    """
    Metadata about agent execution for observability and debugging.
    """
    agent_id: str = field(default_factory=lambda: str(uuid4()))
    agent_type: str = "generic"  # e.g., "scout", "synthesizer", "evaluator"
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_latency_ms: float = 0.0
    
    # Tool execution trace
    tools_called: List[ToolName] = field(default_factory=list)
    tools_succeeded: List[ToolName] = field(default_factory=list)
    tools_failed: List[ToolName] = field(default_factory=list)
    
    # Recovery info
    recovery_triggered: bool = False
    recovery_strategy: Optional[RecoveryStrategy] = None
    
    # Reasoning trace (optional, for transparency)
    reasoning_trace: Optional[str] = None


# ============================================================================
# Agent Input/Output Contracts
# ============================================================================

@dataclass(frozen=True)
class AgentInput:
    """
    Input contract: what every agent receives (immutable).
    Agents are stateless functions: AgentInput → AgentOutput
    """
    query: str  # User's original query or search term
    market: str  # e.g., "nike.com", or market identifier
    context: Dict[str, Any] = field(default_factory=dict)  # Optional context from previous agents
    config: Optional["ToolConfig"] = None
    request_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(frozen=True)
class AgentOutput:
    """
    Output contract: what every agent returns (immutable event).
    This is pushed to event queue/store, consumed by orchestrator/downstream agents.
    """
    request_id: str  # Correlates with input
    agent_id: str
    status: AgentStatus
    
    # The actual result data
    result: Any  # Could be List[Product], List[SearchResult], synthesized data, etc.
    
    # Recovery & auditing
    recovery_log: List[RecoveryEvent] = field(default_factory=list)
    metadata: AgentMetadata = field(default_factory=AgentMetadata)
    
    # Error details if failed
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    
    # Timestamps
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
# Tool Configuration
# ============================================================================

@dataclass(frozen=True)
class ToolConfig:
    """
    Configuration for tool execution.
    Passed from orchestrator to agents.
    """
    # Retry policy
    max_retries: int = 3
    timeout_seconds: float = 30.0
    
    # Fallback strategy
    enable_fallbacks: bool = True
    fallback_timeout_seconds: float = 60.0
    
    # Caching
    use_cache: bool = True
    cache_ttl_seconds: int = 3600
    
    # Tool-specific settings
    tool_settings: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# System State (for orchestrator/event store)
# ============================================================================

@dataclass(frozen=True)
class SystemState:
    """
    Immutable snapshot of system state at a point in time.
    Used by orchestrator to track active agents, pending queries, etc.
    """
    request_id: str
    query: str
    market: str
    
    # Current status
    overall_status: AgentStatus
    
    # Agents involved
    completed_agents: List[str] = field(default_factory=list)  # agent_ids
    pending_agents: List[str] = field(default_factory=list)
    failed_agents: List[str] = field(default_factory=list)
    
    # Aggregated results from all agents
    aggregated_result: Optional[Any] = None
    
    # Complete recovery log (combined from all agents)
    full_recovery_log: List[RecoveryEvent] = field(default_factory=list)
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
