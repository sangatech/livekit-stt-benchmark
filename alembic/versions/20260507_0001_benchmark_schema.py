"""benchmark schema

Revision ID: 20260507_0001
Revises:
Create Date: 2026-05-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260507_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benchmark_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("primary_provider", sa.String(length=64), nullable=False),
        sa.Column("secondary_provider", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
    )
    op.create_table(
        "benchmark_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("benchmark_sessions.id"), nullable=True),
        sa.Column("call_id", sa.String(length=128), nullable=False),
        sa.Column("room_id", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audio_duration_ms", sa.Float(), nullable=True),
        sa.Column("raw_audio_uri", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
    )
    op.create_index("ix_benchmark_calls_call_id", "benchmark_calls", ["call_id"], unique=True)
    op.create_index("ix_benchmark_calls_room_id", "benchmark_calls", ["room_id"])
    op.create_table(
        "benchmark_provider_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id_fk", sa.Integer(), sa.ForeignKey("benchmark_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("final_transcript", sa.Text(), nullable=True),
        sa.Column("avg_confidence", sa.Float(), nullable=True),
        sa.Column("avg_latency_ms", sa.Float(), nullable=True),
        sa.Column("first_partial_latency_ms", sa.Float(), nullable=True),
        sa.Column("first_final_latency_ms", sa.Float(), nullable=True),
        sa.Column("endpointing_delay_ms", sa.Float(), nullable=True),
        sa.Column("partial_rewrites", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reconnects", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("disconnects", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("packet_loss_indicators", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_events_uri", sa.Text(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
    )
    op.create_index("ix_benchmark_provider_results_provider", "benchmark_provider_results", ["provider"])
    op.create_table(
        "benchmark_transcript_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id_fk", sa.Integer(), sa.ForeignKey("benchmark_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("sequence_id", sa.Integer(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("is_final", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_event", sa.JSON(), nullable=True),
    )
    op.create_index("ix_benchmark_transcript_events_provider", "benchmark_transcript_events", ["provider"])
    op.create_table(
        "benchmark_latency_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id_fk", sa.Integer(), sa.ForeignKey("benchmark_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("value_ms", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
    )
    op.create_index("ix_benchmark_latency_metrics_provider", "benchmark_latency_metrics", ["provider"])


def downgrade() -> None:
    op.drop_table("benchmark_latency_metrics")
    op.drop_table("benchmark_transcript_events")
    op.drop_table("benchmark_provider_results")
    op.drop_index("ix_benchmark_calls_room_id", table_name="benchmark_calls")
    op.drop_index("ix_benchmark_calls_call_id", table_name="benchmark_calls")
    op.drop_table("benchmark_calls")
    op.drop_table("benchmark_sessions")
