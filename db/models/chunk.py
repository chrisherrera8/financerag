import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from db.base import Base

if TYPE_CHECKING:
    from db.models.filing import Filing


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint(
            "chunk_level IN ('document', 'section', 'paragraph', 'sentence')",
            name="chunks_chunk_level_check",
        ),
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    filing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("filings.filing_id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.chunk_id", ondelete="CASCADE")
    )
    chunk_level: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(Text)
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))

    # Denormalized from filings — populated and kept in sync by DB triggers.
    # Do not set these directly; set filing_id instead.
    ticker: Mapped[str] = mapped_column(Text, nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer)
    filing_type: Mapped[str] = mapped_column(Text, nullable=False)

    section_name: Mapped[str | None] = mapped_column(Text)
    section_order: Mapped[int | None] = mapped_column(Integer)
    chunk_sequence: Mapped[int | None] = mapped_column(Integer)

    financial_metrics_mentioned: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    business_segments_mentioned: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    geographic_regions_mentioned: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    filing: Mapped["Filing"] = relationship(back_populates="chunks")
    children: Mapped[list["Chunk"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        foreign_keys="Chunk.parent_chunk_id",
    )
    parent: Mapped["Chunk | None"] = relationship(
        back_populates="children",
        remote_side="Chunk.chunk_id",
        foreign_keys="Chunk.parent_chunk_id",
    )
