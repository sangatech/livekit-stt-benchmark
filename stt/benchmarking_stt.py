from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from livekit import rtc
from livekit.agents import stt
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, NotGivenOr
from livekit.agents.utils import AudioBuffer

from benchmark.client import BenchmarkHttpPublisher

logger = logging.getLogger(__name__)


class BenchmarkingSTT(stt.STT):
    """Tee a LiveKit STT stream into primary and shadow providers.

    Primary events are returned to AgentSession. Shadow events are only published
    to the benchmark dashboard.
    """

    def __init__(
        self,
        *,
        primary_stt: stt.STT,
        primary_provider: str,
        shadow_stt: stt.STT,
        shadow_provider: str,
        call_id: str,
        room_id: str,
        publisher: BenchmarkHttpPublisher | None = None,
    ) -> None:
        super().__init__(capabilities=primary_stt.capabilities)
        self._primary_stt = primary_stt
        self._shadow_stt = shadow_stt
        self._primary_provider = primary_provider
        self._shadow_provider = shadow_provider
        self._call_id = call_id
        self._room_id = room_id
        self._publisher = publisher or BenchmarkHttpPublisher()
        self._recognize_metrics_needed = False

        self._primary_stt.on("metrics_collected", lambda metrics: self.emit("metrics_collected", metrics))
        self._shadow_stt.on("metrics_collected", lambda metrics: self.emit("metrics_collected", metrics))

    @property
    def model(self) -> str:
        return self._primary_stt.model

    @property
    def provider(self) -> str:
        return self._primary_stt.provider

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        return await self._primary_stt.recognize(
            buffer,
            language=language,
            conn_options=conn_options,
        )

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.RecognizeStream:
        return BenchmarkingRecognizeStream(
            benchmarking_stt=self,
            primary_stt=self._primary_stt,
            primary_provider=self._primary_provider,
            shadow_stt=self._shadow_stt,
            shadow_provider=self._shadow_provider,
            call_id=self._call_id,
            room_id=self._room_id,
            publisher=self._publisher,
            language=language,
            conn_options=conn_options,
        )

    async def aclose(self) -> None:
        for provider_stt in (self._primary_stt, self._shadow_stt):
            close = getattr(provider_stt, "aclose", None)
            if close is not None:
                await close()


class BenchmarkingRecognizeStream(stt.RecognizeStream):
    def __init__(
        self,
        *,
        benchmarking_stt: BenchmarkingSTT,
        primary_stt: stt.STT,
        primary_provider: str,
        shadow_stt: stt.STT,
        shadow_provider: str,
        call_id: str,
        room_id: str,
        publisher: BenchmarkHttpPublisher,
        language: NotGivenOr[str],
        conn_options: APIConnectOptions,
    ) -> None:
        self._primary_stt = primary_stt
        self._shadow_stt = shadow_stt
        self._primary_provider = primary_provider
        self._shadow_provider = shadow_provider
        self._call_id = call_id
        self._room_id = room_id
        self._publisher = publisher
        self._language = language
        self._provider_sequences = {primary_provider: 0, shadow_provider: 0}
        self._first_audio_at: float | None = None
        self._shadow_audio_disabled = False
        super().__init__(stt=benchmarking_stt, conn_options=conn_options)

    async def _run(self) -> None:
        primary_stream = self._primary_stt.stream(
            language=self._language,
            conn_options=self._conn_options,
        )
        shadow_stream = self._shadow_stt.stream(
            language=self._language,
            conn_options=self._conn_options,
        )

        tasks = [
            asyncio.create_task(self._fanout_audio(primary_stream, shadow_stream), name="stt-audio-fanout"),
            asyncio.create_task(
                self._consume_primary(primary_stream, self._primary_provider),
                name=f"stt-primary-{self._primary_provider}",
            ),
            asyncio.create_task(
                self._consume_shadow(shadow_stream, self._shadow_provider),
                name=f"stt-shadow-{self._shadow_provider}",
            ),
        ]

        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for task in done:
                exc = task.exception()
                if exc is not None:
                    raise exc
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            for stream in (primary_stream, shadow_stream):
                close = getattr(stream, "aclose", None)
                if close is not None:
                    await close()

    async def _fanout_audio(self, primary_stream: stt.RecognizeStream, shadow_stream: stt.RecognizeStream) -> None:
        async for item in self._input_ch:
            if isinstance(item, stt.RecognizeStream._FlushSentinel):
                primary_stream.flush()
                self._safe_shadow_stream_call(shadow_stream, "flush")
            else:
                frame = item
                if self._first_audio_at is None:
                    self._first_audio_at = time.monotonic()
                primary_stream.push_frame(frame)
                self._safe_shadow_stream_call(shadow_stream, "push_frame", frame)

        primary_stream.end_input()
        self._safe_shadow_stream_call(shadow_stream, "end_input")

    def _safe_shadow_stream_call(self, stream: stt.RecognizeStream, method_name: str, *args: Any) -> None:
        if self._shadow_audio_disabled:
            return
        try:
            getattr(stream, method_name)(*args)
        except Exception as exc:
            self._shadow_audio_disabled = True
            logger.warning(
                "disabling shadow STT audio fanout after %s failed provider=%s error=%s",
                method_name,
                self._shadow_provider,
                exc,
            )

    async def _consume_primary(self, stream: stt.RecognizeStream, provider: str) -> None:
        async for event in stream:
            self._publish_event_background(provider, event)
            self._event_ch.send_nowait(event)

    async def _consume_shadow(self, stream: stt.RecognizeStream, provider: str) -> None:
        try:
            async for event in stream:
                self._publish_event_background(provider, event)
        except Exception:
            logger.exception("shadow STT stream failed for provider=%s", provider)

    def _publish_event_background(self, provider: str, event: stt.SpeechEvent) -> None:
        task = asyncio.create_task(self._publish_event(provider, event))
        task.add_done_callback(_log_publish_failure)

    async def _publish_event(self, provider: str, event: stt.SpeechEvent) -> None:
        transcript = _event_transcript(event)
        if not transcript:
            return
        payload = {
            "provider": provider,
            "transcript": transcript,
            "is_final": event.type == stt.SpeechEventType.FINAL_TRANSCRIPT,
            "confidence": _event_confidence(event),
            "timestamp": time.time(),
            "latency_ms": _latency_ms(self._first_audio_at),
            "sequence_id": self._provider_sequences[provider],
            "call_id": self._call_id,
            "room_id": self._room_id,
            "raw": {
                "event_type": str(event.type.value if hasattr(event.type, "value") else event.type),
                "request_id": event.request_id,
                "source": "benchmarking_stt_tee",
            },
        }
        self._provider_sequences[provider] += 1
        try:
            await self._publisher.publish_transcript(payload)
        except Exception:
            logger.exception("failed to publish benchmark STT event provider=%s", provider)


def _event_transcript(event: stt.SpeechEvent) -> str:
    if not event.alternatives:
        return ""
    return event.alternatives[0].text or ""


def _event_confidence(event: stt.SpeechEvent) -> float | None:
    if not event.alternatives:
        return None
    confidence = event.alternatives[0].confidence
    return None if confidence is None else float(confidence)


def _latency_ms(started_at: float | None) -> float | None:
    if started_at is None:
        return None
    return max(0.0, (time.monotonic() - started_at) * 1000.0)


def _log_publish_failure(task: asyncio.Task[Any]) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        exc = task.exception()
        if exc is not None:
            logger.exception("benchmark publish task failed", exc_info=exc)
