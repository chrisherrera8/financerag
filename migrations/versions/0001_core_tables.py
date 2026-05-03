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
            filing_date         DATE NOT NULL,
            period_end_date     DATE,
            fiscal_year         INT NOT NULL,
            fiscal_quarter      INT,  -- nullable: 10-Ks have no quarter, 10-Qs do
            created_at          TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("CREATE INDEX ON filings (ticker, fiscal_year, fiscal_quarter)")
    # Note: no separate index on accession_number; the UNIQUE constraint already creates one.

    # Chunk-level data. Filing metadata lives in `filings`; the four denormalized
    # columns below (ticker, fiscal_year, fiscal_quarter, filing_type) are mirrored
    # here to keep ANN pre-filter queries on a single table.
    #
    # INVARIANT: chunks.{ticker, fiscal_year, fiscal_quarter, filing_type} MUST equal
    # the corresponding columns on the referenced filings row. This is enforced by
    # the trigger defined below. Application code should NEVER write these columns
    # directly during normal operation — they are populated/maintained by the trigger.
    op.execute("""
        CREATE TABLE chunks (
            chunk_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            filing_id           UUID NOT NULL REFERENCES filings(filing_id) ON DELETE CASCADE,
            parent_chunk_id     UUID REFERENCES chunks(chunk_id) ON DELETE CASCADE,
            chunk_level         TEXT NOT NULL CHECK (chunk_level IN ('document', 'section', 'paragraph', 'sentence')),
            content             TEXT NOT NULL,
            content_hash        TEXT,
            token_count         INT,
            embedding           VECTOR(1536),

            -- Denormalized from filings for ANN pre-filter performance.
            -- Kept in sync by the chunks_sync_filing_metadata trigger below.
            ticker              TEXT NOT NULL,
            fiscal_year         INT NOT NULL,
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
    op.execute("CREATE INDEX ON chunks (parent_chunk_id)")

    # --- Denormalization sync trigger ---------------------------------------
    # On INSERT/UPDATE of a chunk, populate the denormalized columns from the
    # parent filing. This makes the denormalization invisible to application
    # code: callers only need to set filing_id, and the four mirrored columns
    # are filled in automatically.
    op.execute("""
        CREATE OR REPLACE FUNCTION chunks_populate_filing_metadata()
        RETURNS TRIGGER AS $$
        BEGIN
            SELECT f.ticker, f.fiscal_year, f.fiscal_quarter, f.filing_type
              INTO NEW.ticker, NEW.fiscal_year, NEW.fiscal_quarter, NEW.filing_type
              FROM filings f
             WHERE f.filing_id = NEW.filing_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'filing_id % not found in filings', NEW.filing_id;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER chunks_sync_filing_metadata
        BEFORE INSERT OR UPDATE OF filing_id ON chunks
        FOR EACH ROW
        EXECUTE FUNCTION chunks_populate_filing_metadata();
    """)

    # When a filing's denormalized fields change, propagate to all its chunks.
    # SEC filings rarely get corrected, but tickers change on M&A and accession
    # numbers can be amended — so we handle it rather than hoping it never happens.
    op.execute("""
        CREATE OR REPLACE FUNCTION filings_propagate_metadata_to_chunks()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.ticker         IS DISTINCT FROM OLD.ticker
            OR NEW.fiscal_year    IS DISTINCT FROM OLD.fiscal_year
            OR NEW.fiscal_quarter IS DISTINCT FROM OLD.fiscal_quarter
            OR NEW.filing_type    IS DISTINCT FROM OLD.filing_type THEN
                UPDATE chunks
                   SET ticker         = NEW.ticker,
                       fiscal_year    = NEW.fiscal_year,
                       fiscal_quarter = NEW.fiscal_quarter,
                       filing_type    = NEW.filing_type
                 WHERE filing_id = NEW.filing_id;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER filings_sync_to_chunks
        AFTER UPDATE ON filings
        FOR EACH ROW
        EXECUTE FUNCTION filings_propagate_metadata_to_chunks();
    """)

    # --- Ingestion observability --------------------------------------------
    op.execute("""
        CREATE TABLE ingestion_log (
            id                  BIGSERIAL PRIMARY KEY,
            file_path           TEXT NOT NULL UNIQUE,
            filing_id           UUID REFERENCES filings(filing_id) ON DELETE SET NULL,
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
    op.execute("DROP TRIGGER IF EXISTS filings_sync_to_chunks ON filings")
    op.execute("DROP FUNCTION IF EXISTS filings_propagate_metadata_to_chunks()")
    op.execute("DROP TRIGGER IF EXISTS chunks_sync_filing_metadata ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_populate_filing_metadata()")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS filings")