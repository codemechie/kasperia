from typing import List

from contracts.models import TelemetryPayload


def validate_telemetry_batch(payloads: List[TelemetryPayload]) -> None:
    for p in payloads:
        if not p.entity_id:
            raise ValueError(f"TelemetryPayload missing entity_id: {p}")
        if not p.source_system:
            raise ValueError(f"TelemetryPayload missing source_system: {p}")
