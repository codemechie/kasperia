from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Literal, Union
from abc import ABC, abstractmethod

from contracts.models import ToolName, ToolResponse

FailureMode = Literal["none", "error", "timeout", "rate_limited"]


@dataclass
class ToolScenario:
    failure_mode: FailureMode = "none"
    failure_probability: float = 0.0
    latency_range: tuple[float, float] = (0.05, 0.3)
    force_status: Optional[Literal["success", "error", "timeout", "rate_limited"]] = None


ToolScenarioMap = Dict[ToolName, ToolScenario]


@dataclass
class ExecutionResult:
    response: Optional[ToolResponse]
    strategy: str
    total_latency_ms: float = 0.0
    attempt_count: int = 1
    error_message: Optional[str] = None


class MockTool(ABC):
    @property
    @abstractmethod
    def tool_name(self) -> ToolName: ...

    @abstractmethod
    async def execute(
        self,
        query: str,
        market: str,
        scenario: Optional[ToolScenario] = None,
    ) -> ToolResponse: ...
