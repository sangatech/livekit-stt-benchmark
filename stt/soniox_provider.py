from __future__ import annotations

import os
from typing import Any, AsyncIterator

from benchmark.settings import setting

from .base_provider import AudioFrameEnvelope, STTProvider, STTTranscriptEvent, monotonic_latency_ms
from .deepgram_provider import _normalize_livekit_event
from .keyterms import load_session_keyterms


class SonioxProvider(STTProvider):
    provider_name = "soniox"

    def __init__(self, *, call_id: str | None = None, room_id: str | None = None) -> None:
        super().__init__(call_id=call_id, room_id=room_id)
        self.model = str(setting("soniox_stt_model", os.getenv("SONIOX_STT_MODEL", "stt-rt-v4")))
        self.max_endpoint_delay_ms = int(setting("soniox_max_endpoint_delay_ms", os.getenv("SONIOX_MAX_ENDPOINT_DELAY_MS", "500")))

    def livekit_stt(self) -> Any:
        from livekit.plugins import soniox

        keyterms = load_session_keyterms(provider=self.provider_name, model=self.model)
        context = soniox.ContextObject(terms=keyterms) if keyterms else None
        return soniox.STT(
            api_key=os.getenv("SONIOX_API_KEY") or os.getenv("SENIOX_API_KEY"),
            params=soniox.STTOptions(
                model=self.model,
                language_hints=["en"],
                language_hints_strict=True,
                context=context,
                enable_language_identification=False,
                enable_speaker_diarization=False,
                max_endpoint_delay_ms=self.max_endpoint_delay_ms,
            ),
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
                    raise RuntimeError("Soniox LiveKit STT stream does not expose push_frame/push")
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
                    latency_ms=monotonic_latency_ms(first_frame_at),
                )
                if normalized is not None:
                    sequence_id += 1
                    yield normalized
        finally:
            feeder.cancel()
            close = getattr(stream, "aclose", None)
            if close:
                await close()
