import logging

import pytest

from db.models import IngestionLog
from pipeline.scanner import scan_data_directory
from tests.conftest import sha256_bytes

CONTENT = b"<html>filing</html>"


@pytest.fixture()
def htm(data_dir):
    path = data_dir / "AAPL" / "10-K" / "0000320193-24-000123" / "filing.htm"
    path.write_bytes(CONTENT)
    return path


@pytest.mark.parametrize(
    "existing_hash,existing_status,expected_status",
    [
        (None, None, "NEW"),
        (sha256_bytes(b"<html>old</html>"), "INGESTED", "HASH_MISMATCH"),
    ],
    ids=["new_file", "hash_changed_file"],
)
def test_scan_status(session, data_dir, htm, existing_hash, existing_status, expected_status, caplog):
    if existing_hash is not None:
        session.add(IngestionLog(file_path=str(htm), content_hash=existing_hash, status=existing_status))
        session.commit()

    with caplog.at_level(logging.INFO):
        results = scan_data_directory(data_dir, session)

    assert len(results) == 1
    file_path, content_hash, status = results[0]
    assert file_path == str(htm)
    assert content_hash == sha256_bytes(CONTENT)
    assert status == expected_status

    log_record = next(r for r in caplog.records if expected_status in r.message)
    assert log_record.levelno == logging.INFO
    assert str(htm) in log_record.message


def test_skipped_file_logged_as_warning(session, data_dir, htm, caplog):
    session.add(IngestionLog(file_path=str(htm), content_hash=sha256_bytes(CONTENT), status="INGESTED"))
    session.commit()

    with caplog.at_level(logging.INFO):
        results = scan_data_directory(data_dir, session)

    assert len(results) == 1
    _, _, status = results[0]
    assert status == "SKIPPED"

    log_record = next(r for r in caplog.records if "SKIPPED" in r.message)
    assert log_record.levelno == logging.WARNING
    assert str(htm) in log_record.message


def test_empty_directory(session, tmp_path):
    empty = tmp_path / "data"
    empty.mkdir()

    results = scan_data_directory(empty, session)

    assert results == []
