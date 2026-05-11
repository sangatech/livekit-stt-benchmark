"""cascade benchmark call child rows

Revision ID: 20260511_0003
Revises: 20260508_0002
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op

revision = "20260511_0003"
down_revision = "20260508_0002"
branch_labels = None
depends_on = None


CHILD_FOREIGN_KEYS = (
    (
        "benchmark_provider_results",
        "benchmark_provider_results_call_id_fk_fkey",
    ),
    (
        "benchmark_transcript_events",
        "benchmark_transcript_events_call_id_fk_fkey",
    ),
    (
        "benchmark_latency_metrics",
        "benchmark_latency_metrics_call_id_fk_fkey",
    ),
    (
        "benchmark_reference_transcripts",
        "benchmark_reference_transcripts_call_id_fk_fkey",
    ),
)


def upgrade() -> None:
    for table_name, constraint_name in CHILD_FOREIGN_KEYS:
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")
        op.create_foreign_key(
            constraint_name,
            table_name,
            "benchmark_calls",
            ["call_id_fk"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table_name, constraint_name in CHILD_FOREIGN_KEYS:
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")
        op.create_foreign_key(
            constraint_name,
            table_name,
            "benchmark_calls",
            ["call_id_fk"],
            ["id"],
        )
