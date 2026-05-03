"""numeric tables: financial_metrics, segment_metrics

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-02
"""

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute("""
        CREATE TABLE financial_metrics (
            id                  BIGSERIAL PRIMARY KEY,
            company             TEXT NOT NULL,
            ticker              TEXT NOT NULL,
            fiscal_year         INT NOT NULL,
            fiscal_quarter      INT,
            period_end_date     DATE NOT NULL,
            metric_name         TEXT NOT NULL,
            xbrl_concept        TEXT,
            value               NUMERIC,
            unit                TEXT DEFAULT 'USD',
            scale               TEXT DEFAULT 'millions',
            source_accession    TEXT NOT NULL,
            source_section      TEXT,
            created_at          TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX ON financial_metrics (ticker, fiscal_year, fiscal_quarter)")
    op.execute("CREATE INDEX ON financial_metrics (metric_name, ticker)")

    op.execute("""
        CREATE TABLE segment_metrics (
            id                  BIGSERIAL PRIMARY KEY,
            company             TEXT NOT NULL,
            ticker              TEXT NOT NULL,
            fiscal_year         INT NOT NULL,
            fiscal_quarter      INT,
            period_end_date     DATE NOT NULL,
            dimension           TEXT NOT NULL,
            dimension_value     TEXT NOT NULL,
            metric_name         TEXT NOT NULL,
            value               NUMERIC,
            unit                TEXT DEFAULT 'USD',
            scale               TEXT DEFAULT 'millions',
            source_accession    TEXT NOT NULL,
            created_at          TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX ON segment_metrics (ticker, fiscal_year, dimension, dimension_value)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS segment_metrics")
    op.execute("DROP TABLE IF EXISTS financial_metrics")
