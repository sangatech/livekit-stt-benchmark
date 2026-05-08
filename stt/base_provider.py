from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional


@dataclass(slots=True)
class STTTranscriptEvent:
    provider: str
    transcript: str
    is_final: bool
    confidence: Optional[float]
    timestamp: float
    latency_ms: Optional[float]
    sequence_id: int
    call_id: Optional[str] = None
    room_id: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "transcript": self.transcript,
            "is_final": self.is_final,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "latency_ms": self.latency_ms,
            "sequence_id": self.sequence_id,
            "call_id": self.call_id,
            "room_id": self.room_id,
            "raw": self.raw,
        }


@dataclass(slots=True)
class AudioFrameEnvelope:
    sequence_id: int
    frame: Any
    timestamp: float = field(default_factory=time.monotonic)
    duration_ms: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class STTProvider(ABC):
    provider_name: str

    def __init__(self, *, call_id: str | None = None, room_id: str | None = None) -> None:
        self.call_id = call_id
        self.room_id = room_id

    @abstractmethod
    def livekit_stt(self) -> Any:
        """Return a LiveKit Agents STT instance for the primary production path."""

    @abstractmethod
    async def stream(self, frames: AsyncIterator[AudioFrameEnvelope]) -> AsyncIterator[STTTranscriptEvent]:
        """Consume mirrored audio frames and yield provider-agnostic transcript events."""


def monotonic_latency_ms(started_at: float | None) -> float | None:
    if started_at is None:
        return None
    return max(0.0, (time.monotonic() - started_at) * 1000.0)
