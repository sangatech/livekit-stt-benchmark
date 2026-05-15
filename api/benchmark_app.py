from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from datetime import datetime, time, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import make_url

from benchmark.database import database_url
from benchmark.engine import BenchmarkEngine
from benchmark.reporting import build_call_report_data, build_overall_report_data, filtered_wer_summary, render_call_report_html, render_overall_report_html
from benchmark.repository import BenchmarkRepository
from benchmark.settings import load_settings, save_settings
from stt.provider_manager import PROVIDERS


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


@app.get("/api/benchmark/calls/{call_id}/turns")
async def call_turns(call_id: str) -> dict[str, object]:
    turns = repository.call_turns(call_id)
    if turns is None:
        raise HTTPException(status_code=404, detail="call not found")
    return turns


@app.post("/api/benchmark/calls/{call_id}/turns/{turn_index}/reference")
async def save_reference(call_id: str, turn_index: int, payload: dict[str, Any]) -> dict[str, object]:
    reference = str(payload.get("reference_transcript") or "").strip()
    try:
        return repository.save_reference_transcript(
            call_id=call_id,
            turn_index=turn_index,
            reference_transcript=reference,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/benchmark/calls/{call_id}/reference")
async def save_call_reference(call_id: str, payload: dict[str, Any]) -> dict[str, object]:
    reference = str(payload.get("reference_transcript") or "").strip()
    try:
        return repository.save_call_reference_transcript(
            call_id=call_id,
            reference_transcript=reference,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/benchmark/calls/{call_id}/events")
async def delete_transcript_events(call_id: str, payload: dict[str, Any]) -> dict[str, object]:
    event_ids = [int(event_id) for event_id in payload.get("event_ids", []) if event_id is not None]
    try:
        return repository.delete_transcript_events(call_id=call_id, event_ids=event_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/benchmark/wer/summary")
async def wer_summary() -> dict[str, object]:
    return repository.wer_summary()


@app.get("/api/benchmark/report")
async def overall_report(
    date_from: str = "",
    date_to: str = "",
    search: str = "",
    provider: str = "",
    primary_provider: str = "",
    secondary_provider: str = "",
    reviewed_only: bool = False,
    limit: int = 500,
) -> dict[str, object]:
    filters = {
        "date_from": date_from,
        "date_to": date_to,
        "search": search,
        "provider": provider,
        "primary_provider": primary_provider,
        "secondary_provider": secondary_provider,
        "reviewed_only": reviewed_only,
        "limit": max(1, min(limit, 1000)),
    }
    call_reports = []
    for detail, turns in repository.report_calls(
        limit=filters["limit"],
        started_from=_parse_report_date(date_from, end_of_day=False),
        started_to=_parse_report_date(date_to, end_of_day=True),
        search=search,
        provider=_normalize_provider_filter(provider),
        primary_provider=_normalize_provider_filter(primary_provider),
        secondary_provider=_normalize_provider_filter(secondary_provider),
        reviewed_only=reviewed_only,
    ):
        call_reports.append(
            build_call_report_data(
                call_detail=detail,
                call_turns=turns,
                all_calls_wer={},
            )
        )
    all_calls_wer = filtered_wer_summary(call_reports)
    return build_overall_report_data(call_reports=call_reports, all_calls_wer=all_calls_wer, filters=filters)


@app.get("/api/benchmark/report.html", response_class=HTMLResponse)
async def overall_report_html(
    date_from: str = "",
    date_to: str = "",
    search: str = "",
    provider: str = "",
    primary_provider: str = "",
    secondary_provider: str = "",
    reviewed_only: bool = False,
    limit: int = 500,
) -> HTMLResponse:
    report = await overall_report(
        date_from=date_from,
        date_to=date_to,
        search=search,
        provider=provider,
        primary_provider=primary_provider,
        secondary_provider=secondary_provider,
        reviewed_only=reviewed_only,
        limit=limit,
    )
    return HTMLResponse(render_overall_report_html(report))


@app.get("/api/benchmark/calls/{call_id}/report")
async def call_report(call_id: str) -> dict[str, object]:
    detail = repository.call_detail(call_id)
    turns = repository.call_turns(call_id)
    if detail is None or turns is None:
        raise HTTPException(status_code=404, detail="call not found")
    return build_call_report_data(
        call_detail=detail,
        call_turns=turns,
        all_calls_wer=repository.wer_summary(),
    )


@app.get("/api/benchmark/calls/{call_id}/report.html", response_class=HTMLResponse)
async def call_report_html(call_id: str) -> HTMLResponse:
    report = await call_report(call_id)
    return HTMLResponse(render_call_report_html(report))


@app.get("/api/settings")
async def settings() -> dict[str, object]:
    return {
        "settings": load_settings(),
        "providers": sorted(PROVIDERS),
        "modes": ["production", "shadow", "comparison"],
        "deepgram_models": ["nova-2", "nova-3", "nova-2-general"],
        "speechmatics_operating_points": ["enhanced", "standard"],
        "soniox_models": ["stt-rt-v4"],
    }


@app.post("/api/settings")
async def update_settings(payload: dict[str, Any]) -> dict[str, object]:
    return {"settings": save_settings(payload)}


def _normalize_provider_filter(value: str) -> str:
    normalized = value.strip().lower()
    return "soniox" if normalized == "seniox" else normalized


def _parse_report_date(value: str, *, end_of_day: bool) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        if len(value) == 10:
            parsed_date = datetime.strptime(value, "%Y-%m-%d").date()
            parsed_time = time.max if end_of_day else time.min
            return datetime.combine(parsed_date, parsed_time, tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid report date: {value}")


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
