from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)

Base = declarative_base()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BenchmarkSession(Base):
    __tablename__ = "benchmark_sessions"

    id = Column(Integer, primary_key=True)
    mode = Column(String(32), nullable=False)
    primary_provider = Column(String(64), nullable=False)
    secondary_provider = Column(String(64))
    started_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    ended_at = Column(DateTime(timezone=True))
    metadata_json = Column("metadata", JSON)

    calls = relationship("BenchmarkCall", back_populates="session")


class BenchmarkCall(Base):
    __tablename__ = "benchmark_calls"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("benchmark_sessions.id"))
    call_id = Column(String(128), unique=True, index=True, nullable=False)
    room_id = Column(String(128), index=True, nullable=False)
    started_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    ended_at = Column(DateTime(timezone=True))
    audio_duration_ms = Column(Float)
    raw_audio_uri = Column(Text)
    metadata_json = Column("metadata", JSON)

    session = relationship("BenchmarkSession", back_populates="calls")
    provider_results = relationship("BenchmarkProviderResult", back_populates="call")
    transcript_events = relationship("BenchmarkTranscriptEvent", back_populates="call")
    latency_metrics = relationship("BenchmarkLatencyMetric", back_populates="call")
    reference_transcripts = relationship("BenchmarkReferenceTranscript", back_populates="call")


class BenchmarkProviderResult(Base):
    __tablename__ = "benchmark_provider_results"

    id = Column(Integer, primary_key=True)
    call_id_fk = Column(Integer, ForeignKey("benchmark_calls.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(64), index=True, nullable=False)
    final_transcript = Column(Text)
    avg_confidence = Column(Float)
    avg_latency_ms = Column(Float)
    first_partial_latency_ms = Column(Float)
    first_final_latency_ms = Column(Float)
    endpointing_delay_ms = Column(Float)
    partial_rewrites = Column(Integer, default=0, nullable=False)
    reconnects = Column(Integer, default=0, nullable=False)
    disconnects = Column(Integer, default=0, nullable=False)
    packet_loss_indicators = Column(Integer, default=0, nullable=False)
    raw_events_uri = Column(Text)
    summary_json = Column("summary", JSON)

    call = relationship("BenchmarkCall", back_populates="provider_results")


class BenchmarkTranscriptEvent(Base):
    __tablename__ = "benchmark_transcript_events"

    id = Column(Integer, primary_key=True)
    call_id_fk = Column(Integer, ForeignKey("benchmark_calls.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(64), index=True, nullable=False)
    sequence_id = Column(Integer, nullable=False)
    transcript = Column(Text, nullable=False)
    is_final = Column(Boolean, default=False, nullable=False)
    confidence = Column(Float)
    latency_ms = Column(Float)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    raw_event = Column(JSON)

    call = relationship("BenchmarkCall", back_populates="transcript_events")


class BenchmarkLatencyMetric(Base):
    __tablename__ = "benchmark_latency_metrics"

    id = Column(Integer, primary_key=True)
    call_id_fk = Column(Integer, ForeignKey("benchmark_calls.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(64), index=True, nullable=False)
    metric_name = Column(String(128), nullable=False)
    value_ms = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    metadata_json = Column("metadata", JSON)

    call = relationship("BenchmarkCall", back_populates="latency_metrics")


class BenchmarkReferenceTranscript(Base):
    __tablename__ = "benchmark_reference_transcripts"
    __table_args__ = (UniqueConstraint("call_id_fk", "turn_index", name="uq_reference_call_turn"),)

    id = Column(Integer, primary_key=True)
    call_id_fk = Column(Integer, ForeignKey("benchmark_calls.id", ondelete="CASCADE"), nullable=False)
    turn_index = Column(Integer, nullable=False)
    reference_transcript = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    call = relationship("BenchmarkCall", back_populates="reference_transcripts")


def database_url() -> str:
    return os.getenv("BENCHMARK_DATABASE_URL", os.getenv("DATABASE_URL", "sqlite:///benchmark.db"))


def session_factory() -> sessionmaker:
    engine = create_engine(database_url())
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_tables() -> None:
    engine = create_engine(database_url())
    Base.metadata.create_all(engine)
