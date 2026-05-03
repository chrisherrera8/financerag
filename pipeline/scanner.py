import hashlib
import logging
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from db.models import IngestionLog

logger = logging.getLogger(__name__)

Status = Literal["NEW", "SKIPPED", "HASH_MISMATCH"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_data_directory(
    data_dir: Path, session: Session
) -> list[tuple[str, str, Status]]:
    """Walk data_dir for *.htm files and return (file_path, hash, status) tuples."""
    results: list[tuple[str, str, Status]] = []

    for htm_file in sorted(data_dir.rglob("*.htm")):
        file_path = str(htm_file)
        content_hash = _sha256(htm_file)

        row: IngestionLog | None = (
            session.query(IngestionLog)
            .filter(IngestionLog.file_path == file_path)
            .first()
        )

        if row is None:
            status: Status = "NEW"
        elif row.content_hash == content_hash:
            status = "SKIPPED"
        else:
            status = "HASH_MISMATCH"

        if status == "SKIPPED":
            logger.warning("%s %s", status, file_path)
        else:
            logger.info("%s %s", status, file_path)
        results.append((file_path, content_hash, status))

    return results
