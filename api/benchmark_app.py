from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import make_url

from benchmark.database import database_url
from benchmark.engine import BenchmarkEngine
from benchmark.repository import BenchmarkRepository


class BroadcastHub:
    def __init__(self) -> None:
        self._channels: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._channels.setdefault(channel, set()).add(websocket)

    async def disconnect(self, channel: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._channels.get(channel, set()).discard(websocket)

    async def publish(self, channel: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            sockets = list(self._channels.get(channel, set())) + list(self._channels.get("*", set()))
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except RuntimeError:
                await self.disconnect(channel, socket)


hub = BroadcastHub()


async def sink(payload: dict[str, object]) -> None:
    call_id = str(payload.get("call_id") or payload.get("event", {}).get("call_id") or "")
    await hub.publish("benchmark/live", payload)
    if call_id:
        await hub.publish(f"call/{call_id}", payload)
    if payload.get("type") == "transcript":
        await hub.publish("provider-stats", payload)


repository = BenchmarkRepository()
engine = BenchmarkEngine(sink=sink, repository=repository)
app = FastAPI(title="STT Benchmark Dashboard", version="0.1.0")

static_dir = Path(__file__).resolve().parents[1] / "dashboard" / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
async def log_database_target() -> None:
    url = make_url(database_url())
    print(
        "Benchmark database: "
        f"driver={url.drivername} host={url.host or 'local'} "
        f"port={url.port or ''} database={url.database or url.database}"
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/benchmark/calls")
async def calls() -> list[dict[str, object]]:
    calls_by_id = {call["call_id"]: call for call in repository.list_calls(limit=100)}
    for call in engine.active_calls():
        calls_by_id[call["call_id"]] = {**calls_by_id.get(call["call_id"], {}), **call}
    return list(calls_by_id.values())


@app.get("/api/benchmark/calls/{call_id}")
async def call_detail(call_id: str) -> dict[str, object]:
    if call_id in {call["call_id"] for call in engine.active_calls()}:
        summary = engine.summary(call_id)
        stored = repository.call_detail(call_id) or {}
        return {**summary, "events": stored.get("events", [])}
    stored = repository.call_detail(call_id)
    if stored is not None:
        return stored
    return engine.summary(call_id)


@app.post("/api/benchmark/events/transcript")
async def ingest_transcript(event: dict[str, Any]) -> dict[str, object]:
    from stt.base_provider import STTTranscriptEvent

    transcript_event = STTTranscriptEvent(**event)
    return await engine.observe_transcript(transcript_event)


@app.websocket("/ws/benchmark/live")
async def ws_benchmark_live(websocket: WebSocket) -> None:
    await _websocket_loop(websocket, "benchmark/live")


@app.websocket("/ws/call/{call_id}")
async def ws_call(websocket: WebSocket, call_id: str) -> None:
    await _websocket_loop(websocket, f"call/{call_id}")


@app.websocket("/ws/provider-stats")
async def ws_provider_stats(websocket: WebSocket) -> None:
    await _websocket_loop(websocket, "provider-stats")


async def _websocket_loop(websocket: WebSocket, channel: str) -> None:
    await hub.connect(channel, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")
            else:
                await websocket.send_text(json.dumps({"type": "ack"}))
    except WebSocketDisconnect:
        await hub.disconnect(channel, websocket)
