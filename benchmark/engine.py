from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from stt.base_provider import STTTranscriptEvent

from .metrics import MetricsRegistry
from .settings import setting
from .transcript_diff import compare_transcripts

EventSink = Callable[[dict[str, object]], Awaitable[None]]


@dataclass(slots=True)
class BenchmarkCallState:
    call_id: str
    room_id: str
    started_at: float = field(default_factory=time.time)
    provider_events: dict[str, list[STTTranscriptEvent]] = field(default_factory=dict)
    metrics: MetricsRegistry = field(default_factory=MetricsRegistry)


class BenchmarkEngine:
    def __init__(self, *, sink: EventSink | None = None, storage_root: str = "calls", repository=None) -> None:
        self._calls: dict[str, BenchmarkCallState] = {}
        self._lock = asyncio.Lock()
        self._sink = sink
        self._storage_root = Path(storage_root)
        self._repository = repository

    async def start_call(self, *, call_id: str, room_id: str) -> BenchmarkCallState:
        async with self._lock:
            state = self._calls.setdefault(call_id, BenchmarkCallState(call_id=call_id, room_id=room_id))
        if self._repository is not None:
            await asyncio.to_thread(self._repository.ensure_call, call_id=call_id, room_id=room_id)
        await self._emit({"type": "call_started", "call_id": call_id, "room_id": room_id, "timestamp": time.time()})
        return state

    async def observe_transcript(self, event: STTTranscriptEvent) -> dict[str, object]:
        call_id = event.call_id or "unknown"
        room_id = event.room_id or "unknown"
        state = await self.start_call(call_id=call_id, room_id=room_id)
        state.provider_events.setdefault(event.provider, []).append(event)
        provider_metrics = state.metrics.observe_transcript(event)
        if self._repository is not None:
            await asyncio.to_thread(self._repository.save_transcript_event, event)
        payload = {
            "type": "transcript",
            "event": event.as_dict(),
            "provider_metrics": provider_metrics.snapshot(),
            "comparison": self._comparison_snapshot(state),
        }
        await self._emit(payload)
        return payload

    async def end_call(self, call_id: str) -> dict[str, object]:
        state = self._calls.get(call_id)
        if state is None:
            return {"call_id": call_id, "status": "not_found"}
        summary = self.summary(call_id)
        await self.persist_summary(call_id)
        if self._repository is not None:
            await asyncio.to_thread(self._repository.end_call, call_id)
        await self._emit({"type": "call_ended", "call_id": call_id, "summary": summary, "timestamp": time.time()})
        return summary

    def active_calls(self) -> list[dict[str, object]]:
        return [self.summary(call_id) for call_id in self._calls]

    def summary(self, call_id: str) -> dict[str, object]:
        state = self._calls[call_id]
        return {
            "call_id": state.call_id,
            "room_id": state.room_id,
            "started_at": state.started_at,
            "duration_s": max(0.0, time.time() - state.started_at),
            "providers": sorted(state.provider_events),
            "metrics": state.metrics.snapshot(),
            "comparison": self._comparison_snapshot(state),
        }

    async def persist_summary(self, call_id: str) -> None:
        state = self._calls[call_id]
        call_dir = Path(str(setting("benchmark_storage_root", str(self._storage_root)))) / call_id
        call_dir.mkdir(parents=True, exist_ok=True)
        for provider, events in state.provider_events.items():
            (call_dir / f"{provider}.json").write_text(
                json.dumps([event.as_dict() for event in events], indent=2),
                encoding="utf-8",
            )
        (call_dir / "benchmark_summary.json").write_text(
            json.dumps(self.summary(call_id), indent=2),
            encoding="utf-8",
        )

    def _comparison_snapshot(self, state: BenchmarkCallState) -> dict[str, object]:
        finals = {
            provider: events[-1].transcript
            for provider, events in state.provider_events.items()
            if events and events[-1].is_final
        }
        if len(finals) < 2:
            return {"ready": False, "providers": finals}
        providers = sorted(finals)
        return {
            "ready": True,
            "primary_provider": providers[0],
            "secondary_provider": providers[1],
            "diff": compare_transcripts(finals[providers[0]], finals[providers[1]]),
            "transcripts": finals,
        }

    async def _emit(self, payload: dict[str, object]) -> None:
        if self._sink is not None:
            await self._sink(payload)


engine = BenchmarkEngine()
