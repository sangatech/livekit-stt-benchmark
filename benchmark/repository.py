from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from stt.base_provider import STTTranscriptEvent

from .database import BenchmarkCall, BenchmarkTranscriptEvent, session_factory


class BenchmarkRepository:
    def __init__(self, factory: sessionmaker[Session] | None = None) -> None:
        self._factory = factory or session_factory()

    def ensure_call(self, *, call_id: str, room_id: str) -> None:
        with self._factory() as session:
            call = session.query(BenchmarkCall).filter_by(call_id=call_id).one_or_none()
            if call is None:
                session.add(BenchmarkCall(call_id=call_id, room_id=room_id))
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()

    def save_transcript_event(self, event: STTTranscriptEvent) -> None:
        call_id = event.call_id or "unknown"
        room_id = event.room_id or "unknown"
        with self._factory() as session:
            call = session.query(BenchmarkCall).filter_by(call_id=call_id).one_or_none()
            if call is None:
                call = BenchmarkCall(call_id=call_id, room_id=room_id)
                session.add(call)
                try:
                    session.flush()
                except IntegrityError:
                    session.rollback()
                    call = session.query(BenchmarkCall).filter_by(call_id=call_id).one()
            session.add(
                BenchmarkTranscriptEvent(
                    call_id_fk=call.id,
                    provider=event.provider,
                    sequence_id=event.sequence_id,
                    transcript=event.transcript,
                    is_final=event.is_final,
                    confidence=event.confidence,
                    latency_ms=event.latency_ms,
                    timestamp=datetime.fromtimestamp(event.timestamp),
                    raw_event=event.raw,
                )
            )
            session.commit()

    def end_call(self, call_id: str) -> None:
        with self._factory() as session:
            call = session.query(BenchmarkCall).filter_by(call_id=call_id).one_or_none()
            if call is not None:
                call.ended_at = datetime.utcnow()
                session.commit()

    def list_calls(self, *, limit: int = 100) -> list[dict[str, object]]:
        with self._factory() as session:
            calls = (
                session.query(BenchmarkCall)
                .order_by(BenchmarkCall.started_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "call_id": call.call_id,
                    "room_id": call.room_id,
                    "started_at": call.started_at.timestamp() if call.started_at else None,
                    "ended_at": call.ended_at.timestamp() if call.ended_at else None,
                }
                for call in calls
            ]

    def call_detail(self, call_id: str) -> dict[str, object] | None:
        with self._factory() as session:
            call = session.query(BenchmarkCall).filter_by(call_id=call_id).one_or_none()
            if call is None:
                return None
            events = (
                session.query(BenchmarkTranscriptEvent)
                .filter_by(call_id_fk=call.id)
                .order_by(BenchmarkTranscriptEvent.timestamp.asc(), BenchmarkTranscriptEvent.id.asc())
                .all()
            )
            return {
                "call_id": call.call_id,
                "room_id": call.room_id,
                "started_at": call.started_at.timestamp() if call.started_at else None,
                "ended_at": call.ended_at.timestamp() if call.ended_at else None,
                "events": [
                    {
                        "provider": event.provider,
                        "transcript": event.transcript,
                        "is_final": event.is_final,
                        "confidence": event.confidence,
                        "timestamp": event.timestamp.timestamp() if event.timestamp else None,
                        "latency_ms": event.latency_ms,
                        "sequence_id": event.sequence_id,
                        "call_id": call.call_id,
                        "room_id": call.room_id,
                        "raw": event.raw_event or {},
                    }
                    for event in events
                ],
            }
