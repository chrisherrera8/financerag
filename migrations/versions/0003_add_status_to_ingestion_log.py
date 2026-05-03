"""Add status column to ingestion_log

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-02
"""

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ingestion_log
        ADD COLUMN status TEXT NOT NULL DEFAULT 'PENDING'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE ingestion_log DROP COLUMN status")
