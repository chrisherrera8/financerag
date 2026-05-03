"""core tables: filings, chunks, ingestion_log, ingestion_failures

Revision ID: 0001
Revises:
Create Date: 2026-05-02
"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    # Source of truth for all filing-level metadata.
    op.execute("""
        CREATE TABLE filings (
            filing_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            accession_number    TEXT NOT NULL UNIQUE,
            company             TEXT NOT NULL,
            ticker              TEXT NOT NULL,
            filing_type         TEXT NOT NULL,
            filing_date         DATE,
            period_end_date     DATE,
            fiscal_year         INT,
            fiscal_quarter      INT,
            created_at          TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX ON filings (ticker, fiscal_year, fiscal_quarter)")
    op.execute("CREATE INDEX ON filings (accession_number)")

    # Chunk-level data only. Filing metadata lives in filings.
    # The four denormalized columns (ticker, fiscal_year, fiscal_quarter, filing_type)
    # are copied here to keep ANN pre-filter queries on a single table.
    op.execute("""
        CREATE TABLE chunks (
            chunk_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            filing_id           UUID NOT NULL REFERENCES filings(filing_id),
            parent_chunk_id     UUID REFERENCES chunks(chunk_id),
            chunk_level         TEXT NOT NULL CHECK (chunk_level IN ('document', 'section', 'paragraph', 'sentence')),
            content             TEXT NOT NULL,
            content_hash        TEXT,
            token_count         INT,
            embedding           VECTOR(1536),

            -- Denormalized for pre-filter performance during ANN search
            ticker              TEXT NOT NULL,
            fiscal_year         INT,
            fiscal_quarter      INT,
            filing_type         TEXT NOT NULL,

            -- Chunk position within the filing
            section_name        TEXT,
            section_order       INT,
            chunk_sequence      INT,

            -- Extracted signals (chunk-level, not filing-level)
            financial_metrics_mentioned     TEXT[],
            business_segments_mentioned     TEXT[],
            geographic_regions_mentioned    TEXT[],

            created_at          TIMESTAMPTZ DEFAULT now()
        )
    """)

    # ANN index for vector similarity search
    op.execute("CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops)")

    # Pre-filter indexes for common query patterns
    op.execute("CREATE INDEX ON chunks (ticker, fiscal_year, filing_type)")
    op.execute("CREATE INDEX ON chunks (fiscal_quarter)")
    op.execute("CREATE INDEX ON chunks (chunk_level)")
    op.execute("CREATE INDEX ON chunks (filing_id)")

    op.execute("""
        CREATE TABLE ingestion_log (
            id                  BIGSERIAL PRIMARY KEY,
            file_path           TEXT NOT NULL UNIQUE,
            filing_id           UUID REFERENCES filings(filing_id),
            chunk_count         INT,
            content_hash        TEXT,
            ingested_at         TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE ingestion_failures (
            id                  BIGSERIAL PRIMARY KEY,
            file_path           TEXT NOT NULL,
            error_type          TEXT NOT NULL CHECK (error_type IN ('PARSE_ERROR', 'SEGMENT_ERROR', 'EMBED_ERROR', 'DB_WRITE_ERROR')),
            error_message       TEXT,
            failed_at           TIMESTAMPTZ DEFAULT now(),
            retry_count         INT DEFAULT 0,
            resolved            BOOLEAN DEFAULT FALSE
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingestion_failures")
    op.execute("DROP TABLE IF EXISTS ingestion_log")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS filings")
