from __future__ import annotations

import os
import time
from typing import Any, AsyncIterator

from benchmark.settings import setting

from .base_provider import AudioFrameEnvelope, STTProvider, STTTranscriptEvent, monotonic_latency_ms
from .keyterms import load_session_keyterms


class DeepgramProvider(STTProvider):
    provider_name = "deepgram"
    base_provider_name = "deepgram"

    def __init__(self, *, call_id: str | None = None, room_id: str | None = None, role: str = "primary") -> None:
        super().__init__(call_id=call_id, room_id=room_id)
        default_model = str(setting("deepgram_stt_model", os.getenv("DEEPGRAM_STT_MODEL", "nova-2")))
        model_key = f"deepgram_{role}_stt_model"
        env_key = f"DEEPGRAM_{role.upper()}_STT_MODEL"
        self.model = str(setting(model_key, os.getenv(env_key, default_model)) or default_model)

    def livekit_stt(self) -> Any:
        from livekit.plugins import deepgram

        benchmark_mode = str(setting("stt_benchmark_mode", os.getenv("STT_BENCHMARK_MODE", "production"))).lower()
        interim_default = "true" if benchmark_mode in {"shadow", "comparison"} else "false"
        configured_interim = setting("deepgram_interim_results", os.getenv("DEEPGRAM_INTERIM_RESULTS", interim_default))
        interim_results = interim_default.lower() == "true" if configured_interim is None else bool(configured_interim)
        keyterms = load_session_keyterms(provider=self.base_provider_name, model=self.model)
        return deepgram.STT(
            model=self.model,
            language="en",
            interim_results=interim_results,
            smart_format=True,
            keyterm=keyterms,
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
                    raise RuntimeError("Deepgram LiveKit STT stream does not expose push_frame/push")
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


def _normalize_livekit_event(
    event: Any,
    *,
    provider: str,
    sequence_id: int,
    call_id: str | None,
    room_id: str | None,
    latency_ms: float | None,
) -> STTTranscriptEvent | None:
    alternatives = getattr(event, "alternatives", None) or getattr(event, "results", None) or []
    text = ""
    confidence = None
    if alternatives:
        alt = alternatives[0]
        text = getattr(alt, "text", None) or getattr(alt, "transcript", "") or ""
        confidence = getattr(alt, "confidence", None)
    else:
        text = getattr(event, "text", None) or getattr(event, "transcript", "") or ""
        confidence = getattr(event, "confidence", None)
    if not text:
        return None

    event_type = str(getattr(event, "type", "")).lower()
    is_final = bool(
        getattr(event, "is_final", False)
        or getattr(event, "final", False)
        or "final" in event_type
    )
    return STTTranscriptEvent(
        provider=provider,
        transcript=text,
        is_final=is_final,
        confidence=confidence,
        timestamp=time.time(),
        latency_ms=latency_ms,
        sequence_id=sequence_id,
        call_id=call_id,
        room_id=room_id,
        raw={"type": str(getattr(event, "type", ""))},
    )
