from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from stt.base_provider import STTTranscriptEvent

from .database import BenchmarkCall, BenchmarkReferenceTranscript, BenchmarkTranscriptEvent, session_factory
from .transcript_diff import wer_stats


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
                    timestamp=datetime.fromtimestamp(event.timestamp, tz=timezone.utc),
                    raw_event=event.raw,
                )
            )
            session.commit()

    def end_call(self, call_id: str) -> None:
        with self._factory() as session:
            call = session.query(BenchmarkCall).filter_by(call_id=call_id).one_or_none()
            if call is not None:
                call.ended_at = datetime.now(timezone.utc)
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
                        "id": event.id,
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

    def call_turns(self, call_id: str) -> dict[str, object] | None:
        with self._factory() as session:
            call = session.query(BenchmarkCall).filter_by(call_id=call_id).one_or_none()
            if call is None:
                return None
            events = (
                session.query(BenchmarkTranscriptEvent)
                .filter_by(call_id_fk=call.id, is_final=True)
                .order_by(BenchmarkTranscriptEvent.timestamp.asc(), BenchmarkTranscriptEvent.id.asc())
                .all()
            )
            references = {
                reference.turn_index: reference.reference_transcript
                for reference in session.query(BenchmarkReferenceTranscript).filter_by(call_id_fk=call.id).all()
            }
            turns = _build_turns(events, references)
            call_reference = references.get(-1, "")
            provider_transcripts = _call_level_transcripts(events)
            call_level_wer = _provider_wer(call_reference, provider_transcripts)
            return {
                "call_id": call.call_id,
                "room_id": call.room_id,
                "turns": turns,
                "call_reference_transcript": call_reference,
                "call_provider_transcripts": provider_transcripts,
                "call_provider_segments": {
                    provider: len([event for event in events if event.provider == provider])
                    for provider in sorted({event.provider for event in events})
                },
                "call_provider_wer": call_level_wer,
                "wer_summary": _wer_summary(turns),
            }

    def save_reference_transcript(self, *, call_id: str, turn_index: int, reference_transcript: str) -> dict[str, object]:
        with self._factory() as session:
            call = session.query(BenchmarkCall).filter_by(call_id=call_id).one_or_none()
            if call is None:
                raise ValueError(f"call_id not found: {call_id}")
            reference = (
                session.query(BenchmarkReferenceTranscript)
                .filter_by(call_id_fk=call.id, turn_index=turn_index)
                .one_or_none()
            )
            if reference is None:
                reference = BenchmarkReferenceTranscript(
                    call_id_fk=call.id,
                    turn_index=turn_index,
                    reference_transcript=reference_transcript,
                )
                session.add(reference)
            else:
                reference.reference_transcript = reference_transcript
                reference.updated_at = datetime.now(timezone.utc)
            session.commit()
        detail = self.call_turns(call_id)
        if detail is None:
            raise ValueError(f"call_id not found: {call_id}")
        return detail

    def save_call_reference_transcript(self, *, call_id: str, reference_transcript: str) -> dict[str, object]:
        return self.save_reference_transcript(
            call_id=call_id,
            turn_index=-1,
            reference_transcript=reference_transcript,
        )

    def wer_summary(self) -> dict[str, object]:
        provider_totals: dict[str, dict[str, float]] = {}
        reviewed_turns = 0
        reviewed_calls: set[str] = set()
        with self._factory() as session:
            calls = session.query(BenchmarkCall).all()
            for call in calls:
                detail = self.call_turns(call.call_id)
                if detail is None:
                    continue
                reference = str(detail.get("call_reference_transcript") or "").strip()
                if not reference:
                    continue
                reviewed_turns += 1
                reviewed_calls.add(call.call_id)
                for provider, stats in detail.get("call_provider_wer", {}).items():
                    if stats.get("wer") is None:
                        continue
                    totals = provider_totals.setdefault(
                        provider,
                        {"edit_distance": 0.0, "reference_words": 0.0, "turns": 0.0},
                    )
                    totals["edit_distance"] += float(stats.get("edit_distance") or 0)
                    totals["reference_words"] += float(stats.get("reference_words") or 0)
                    totals["turns"] += 1.0
        return {
            "reviewed_calls": len(reviewed_calls),
            "reviewed_turns": reviewed_turns,
            "providers": {
                provider: {
                    "wer": None if totals["reference_words"] == 0 else totals["edit_distance"] / totals["reference_words"],
                    "edit_distance": int(totals["edit_distance"]),
                    "reference_words": int(totals["reference_words"]),
                    "turns": int(totals["turns"]),
                }
                for provider, totals in provider_totals.items()
            },
        }


def _build_turns(events: list[BenchmarkTranscriptEvent], references: dict[int, str]) -> list[dict[str, object]]:
    by_provider: dict[str, list[BenchmarkTranscriptEvent]] = {}
    for event in events:
        by_provider.setdefault(event.provider, []).append(event)
    providers = sorted(by_provider)
    turn_count = max((len(items) for items in by_provider.values()), default=0)
    turns = []
    for turn_index in range(turn_count):
        provider_transcripts = {
            provider: provider_events[turn_index].transcript
            for provider, provider_events in by_provider.items()
            if turn_index < len(provider_events)
        }
        reference = references.get(turn_index, "")
        turns.append(
            {
                "turn_index": turn_index,
                "transcripts": provider_transcripts,
                "reference_transcript": reference,
                "provider_wer": _provider_wer(reference, provider_transcripts),
                "providers": providers,
            }
        )
    return turns


def _call_level_transcripts(events: list[BenchmarkTranscriptEvent]) -> dict[str, str]:
    by_provider: dict[str, list[BenchmarkTranscriptEvent]] = {}
    for event in events:
        by_provider.setdefault(event.provider, []).append(event)
    return {
        provider: " ".join(event.transcript.strip() for event in provider_events if event.transcript.strip())
        for provider, provider_events in by_provider.items()
    }


def _provider_wer(reference: str, provider_transcripts: dict[str, str]) -> dict[str, object]:
    if not reference.strip():
        return {}
    return {
        provider: wer_stats(reference, transcript)
        for provider, transcript in provider_transcripts.items()
        if transcript
    }


def _wer_summary(turns: list[dict[str, object]]) -> dict[str, object]:
    totals: dict[str, dict[str, float]] = {}
    reviewed_turns = 0
    for turn in turns:
        if not str(turn.get("reference_transcript") or "").strip():
            continue
        reviewed_turns += 1
        for provider, stats in turn.get("provider_wer", {}).items():
            if stats.get("wer") is None:
                continue
            provider_total = totals.setdefault(provider, {"edit_distance": 0.0, "reference_words": 0.0, "turns": 0.0})
            provider_total["edit_distance"] += float(stats.get("edit_distance") or 0)
            provider_total["reference_words"] += float(stats.get("reference_words") or 0)
            provider_total["turns"] += 1.0
    return {
        "reviewed_turns": reviewed_turns,
        "providers": {
            provider: {
                "wer": None if total["reference_words"] == 0 else total["edit_distance"] / total["reference_words"],
                "edit_distance": int(total["edit_distance"]),
                "reference_words": int(total["reference_words"]),
                "turns": int(total["turns"]),
            }
            for provider, total in totals.items()
        },
    }
