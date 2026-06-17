from __future__ import annotations

import os
from typing import Any, AsyncIterator

from benchmark.settings import setting

from .base_provider import AudioFrameEnvelope, STTProvider, STTTranscriptEvent
from .deepgram_provider import _normalize_livekit_event
from .keyterms import load_session_keyterms


class SpeechmaticsProvider(STTProvider):
    provider_name = "speechmatics"
    base_provider_name = "speechmatics"

    def __init__(self, *, call_id: str | None = None, room_id: str | None = None, role: str = "primary") -> None:
        super().__init__(call_id=call_id, room_id=room_id)
        default_operating_point = str(setting("speechmatics_operating_point", os.getenv("SPEECHMATICS_OPERATING_POINT", "enhanced")))
        point_key = f"speechmatics_{role}_operating_point"
        env_key = f"SPEECHMATICS_{role.upper()}_OPERATING_POINT"
        self.operating_point = str(setting(point_key, os.getenv(env_key, default_operating_point)) or default_operating_point)
        self.max_delay = float(setting("speechmatics_max_delay", os.getenv("SPEECHMATICS_MAX_DELAY", "1.5")))

    def livekit_stt(self) -> Any:
        from livekit.plugins import speechmatics
        from livekit.plugins.speechmatics import AdditionalVocabEntry, OperatingPoint

        operating_point = (
            OperatingPoint.ENHANCED
            if self.operating_point.lower() == "enhanced"
            else OperatingPoint.STANDARD
        )
        additional_vocab = [
            AdditionalVocabEntry(content=term)
            for term in load_session_keyterms(
                provider=self.base_provider_name,
                model=self.operating_point,
            )
        ]
        return speechmatics.STT(
            operating_point=operating_point,
            language="en",
            max_delay=self.max_delay,
            enable_diarization=False,
            additional_vocab=additional_vocab,
        )

    async def stream(self, frames: AsyncIterator[AudioFrameEnvelope]) -> AsyncIterator[STTTranscriptEvent]:
        stt = self.livekit_stt()
        stream = stt.stream()
        sequence_id = 0
        first_frame_at: float | None = None

        async def feed_audio() -> None:
            nonlocal first_frame_at
            async for envelope in frames:
                first_frame_at = first_frame_at or envelope.timestamp
                push = getattr(stream, "push_frame", None) or getattr(stream, "push", None)
                if push is None:
                    raise RuntimeError("Speechmatics LiveKit STT stream does not expose push_frame/push")
                result = push(envelope.frame)
                if hasattr(result, "__await__"):
                    await result
            end_input = getattr(stream, "end_input", None)
            if end_input:
                result = end_input()
                if hasattr(result, "__await__"):
                    await result

        import asyncio

        feeder = asyncio.create_task(feed_audio())
        try:
            async for event in stream:
                normalized = _normalize_livekit_event(
                    event,
                    provider=self.provider_name,
                    sequence_id=sequence_id,
                    call_id=self.call_id,
                    room_id=self.room_id,
                    latency_ms=None if first_frame_at is None else (envelope_latency_ms(first_frame_at)),
                )
                if normalized is not None:
                    sequence_id += 1
                    yield normalized
        finally:
            feeder.cancel()
            close = getattr(stream, "aclose", None)
            if close:
                await close()


def envelope_latency_ms(started_at: float) -> float:
    import time

    return max(0.0, (time.monotonic() - started_at) * 1000.0)
