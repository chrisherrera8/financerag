from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from db.base import Base


class IngestionFailure(Base):
    __tablename__ = "ingestion_failures"
    __table_args__ = (
        CheckConstraint(
            "error_type IN ('PARSE_ERROR', 'SEGMENT_ERROR', 'EMBED_ERROR', 'DB_WRITE_ERROR')",
            name="ingestion_failures_error_type_check",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    retry_count: Mapped[int] = mapped_column(Integer, server_default="0")
    resolved: Mapped[bool] = mapped_column(Boolean, server_default="false")
