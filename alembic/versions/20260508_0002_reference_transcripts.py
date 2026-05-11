"""reference transcripts

Revision ID: 20260508_0002
Revises: 20260507_0001
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260508_0002"
down_revision = "20260507_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benchmark_reference_transcripts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id_fk", sa.Integer(), sa.ForeignKey("benchmark_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("reference_transcript", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("call_id_fk", "turn_index", name="uq_reference_call_turn"),
    )


def downgrade() -> None:
    op.drop_table("benchmark_reference_transcripts")
