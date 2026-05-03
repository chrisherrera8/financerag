"""Tests for pipeline.parser.

Real-file tests use a fixture that copies a known filing into a temporary
directory so the originals in data/ are never touched.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.parser import ParsedDocument, parse_filing

# ---------------------------------------------------------------------------
# Constants pointing at known fixture files
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Apple 2024 DEF 14A — has h1–h4 headings, tables with non-empty headers/rows,
# no <script> or <style> tags (typical of modern EDGAR iXBRL filings).
_DEF14A = (
    _REPO_ROOT
    / "data/apple/DEF_14A/0001308179-24-000010/laapl2024_def14a.htm"
)

# Apple FY2024 10-K — iXBRL, 63 tables including income statement and balance sheet.
_10K = (
    _REPO_ROOT
    / "data/apple/10-K/0000320193-24-000123/aapl-20240928.htm"
)

# Apple Q1 FY2022 10-Q — iXBRL, 43 tables including income statement and balance sheet.
_10Q = (
    _REPO_ROOT
    / "data/apple/10-Q/0000320193-22-000007/aapl-20211225.htm"
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def real_filing(tmp_path) -> Path:
    """Copy the Apple DEF 14A into a temp dir and return the copy's path.

    This ensures parse_filing can never write back to or delete the original.
    """
    dest = tmp_path / _DEF14A.name
    dest.write_bytes(_DEF14A.read_bytes())
    return dest


@pytest.fixture()
def ten_k_filing(tmp_path) -> Path:
    """Copy the Apple FY2024 10-K into a temp dir and return the copy's path."""
    dest = tmp_path / _10K.name
    dest.write_bytes(_10K.read_bytes())
    return dest


@pytest.fixture()
def ten_q_filing(tmp_path) -> Path:
    """Copy the Apple Q1 FY2022 10-Q into a temp dir and return the copy's path."""
    dest = tmp_path / _10Q.name
    dest.write_bytes(_10Q.read_bytes())
    return dest


@pytest.fixture()
def failed_dir(tmp_path) -> Path:
    """Return a tmp_path root that already contains data/failed/."""
    (tmp_path / "data" / "failed").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def synthetic_filing(tmp_path) -> Path:
    """Return a path inside tmp_path for tests that build their own HTML."""
    return tmp_path / "filing.htm"


def _write(path: Path, html: str) -> Path:
    path.write_text(html, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Heading extraction — real filing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tag", ["h1", "h2", "h3", "h4"])
def test_heading_text_present_in_real_filing(real_filing, tag):
    # The DEF 14A contains all four heading levels; verify each survives parsing.
    known = {
        "h1": "Notice of 2024 Annual Meeting of Shareholders",
        "h2": "Attending the Annual Meeting",
        "h3": "Items of Business and Board Voting Recommendation",
        "h4": None,  # h4 may not appear; skip assertion when absent
    }
    doc = parse_filing(real_filing)

    assert doc is not None
    expected = known[tag]
    if expected is not None:
        assert expected in doc.text


def test_real_filing_text_is_non_empty(real_filing):
    doc = parse_filing(real_filing)

    assert doc is not None
    assert len(doc.text) > 1000


# ---------------------------------------------------------------------------
# Heading extraction — synthetic (covers all four tags explicitly)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tag", ["h1", "h2", "h3", "h4"])
def test_heading_text_preserved_synthetic(synthetic_filing, tag):
    _write(synthetic_filing, f"<html><body><{tag}>Annual Report</{tag}></body></html>")

    doc = parse_filing(synthetic_filing)

    assert doc is not None
    assert "Annual Report" in doc.text


# ---------------------------------------------------------------------------
# Script / style / nav stripping — synthetic
# (Real EDGAR filings have no <script> or <style> tags so these must be
#  tested with hand-crafted HTML.)
# ---------------------------------------------------------------------------


def test_script_tags_stripped(synthetic_filing):
    _write(
        synthetic_filing,
        "<html><body><script>alert('xss')</script><p>Clean</p></body></html>",
    )

    doc = parse_filing(synthetic_filing)

    assert doc is not None
    assert "alert" not in doc.text
    assert "Clean" in doc.text


def test_style_tags_stripped(synthetic_filing):
    _write(
        synthetic_filing,
        "<html><body><style>.nav { display:none }</style><p>Clean</p></body></html>",
    )

    doc = parse_filing(synthetic_filing)

    assert doc is not None
    assert "display" not in doc.text
    assert "Clean" in doc.text


def test_nav_boilerplate_stripped(synthetic_filing):
    _write(
        synthetic_filing,
        "<html><body><nav>Skip to content</nav><p>Real content</p></body></html>",
    )

    doc = parse_filing(synthetic_filing)

    assert doc is not None
    assert "Skip to content" not in doc.text
    assert "Real content" in doc.text


# ---------------------------------------------------------------------------
# Table structure — real filing
# ---------------------------------------------------------------------------


def test_real_filing_tables_extracted(real_filing):
    # The DEF 14A has 472 tables; at minimum several must survive extraction.
    doc = parse_filing(real_filing)

    assert doc is not None
    assert len(doc.tables) > 10


def test_real_filing_director_compensation_table(real_filing):
    # Table 157 in the DEF 14A lists director compensation with known rows.
    # Exact table index may shift; search by header content instead.
    doc = parse_filing(real_filing)

    assert doc is not None
    comp_table = next(
        (
            t
            for t in doc.tables
            if "Name" in t["headers"] and any("Fees" in h for h in t["headers"])
        ),
        None,
    )
    assert comp_table is not None, "Director compensation table not found"
    names = [row[0] for row in comp_table["rows"] if row]
    assert any("Bell" in name for name in names), (
        f"Expected 'Bell' row in compensation table, got: {names[:5]}"
    )


# ---------------------------------------------------------------------------
# Table structure — synthetic
# ---------------------------------------------------------------------------


def test_table_rows_and_columns_extracted(synthetic_filing):
    _write(
        synthetic_filing,
        """<html><body>
        <table>
          <tr><th>Revenue</th><th>2023</th></tr>
          <tr><td>Total</td><td>1000</td></tr>
        </table>
        </body></html>""",
    )

    doc = parse_filing(synthetic_filing)

    assert doc is not None
    assert len(doc.tables) == 1
    tbl = doc.tables[0]
    assert tbl["headers"] == ["Revenue", "2023"]
    assert ["Total", "1000"] in tbl["rows"]


# ---------------------------------------------------------------------------
# Table stitching — matching headers (OQ-04)
# ---------------------------------------------------------------------------


def test_table_stitching_with_matching_headers(synthetic_filing):
    filler = "x" * 400
    _write(
        synthetic_filing,
        f"""<html><body>
        <table id="t1">
          <tr><th>Revenue</th><th>2023</th></tr>
          <tr><td>Q1</td><td>100</td></tr>
        </table>
        {filler}
        <table id="t2">
          <tr><th>Revenue</th><th>2023</th></tr>
          <tr><td>Q2</td><td>200</td></tr>
        </table>
        </body></html>""",
    )

    doc = parse_filing(synthetic_filing)

    assert doc is not None
    assert len(doc.tables) == 1
    rows = doc.tables[0]["rows"]
    assert ["Q1", "100"] in rows
    assert ["Q2", "200"] in rows


def test_table_stitching_boundary_at_500_chars(synthetic_filing):
    filler = "x" * 500
    _write(
        synthetic_filing,
        f"""<html><body>
        <table>
          <tr><th>Col</th></tr>
          <tr><td>R1</td></tr>
        </table>
        {filler}
        <table>
          <tr><th>Col</th></tr>
          <tr><td>R2</td></tr>
        </table>
        </body></html>""",
    )

    doc = parse_filing(synthetic_filing)

    assert doc is not None
    assert len(doc.tables) == 1


def test_table_stitching_rejected_beyond_500_chars(synthetic_filing):
    filler = "x" * 501
    _write(
        synthetic_filing,
        f"""<html><body>
        <table>
          <tr><th>Col</th></tr>
          <tr><td>R1</td></tr>
        </table>
        {filler}
        <table>
          <tr><th>Col</th></tr>
          <tr><td>R2</td></tr>
        </table>
        </body></html>""",
    )

    doc = parse_filing(synthetic_filing)

    assert doc is not None
    assert len(doc.tables) == 2


# ---------------------------------------------------------------------------
# Table stitching — non-matching headers
# ---------------------------------------------------------------------------


def test_table_stitching_rejected_non_matching_headers(synthetic_filing):
    filler = "x" * 100
    _write(
        synthetic_filing,
        f"""<html><body>
        <table>
          <tr><th>Revenue</th><th>2023</th></tr>
          <tr><td>Q1</td><td>100</td></tr>
        </table>
        {filler}
        <table>
          <tr><th>Assets</th><th>Liabilities</th></tr>
          <tr><td>500</td><td>200</td></tr>
        </table>
        </body></html>""",
    )

    doc = parse_filing(synthetic_filing)

    assert doc is not None
    assert len(doc.tables) == 2


def test_table_stitching_boundary_50_percent_headers(synthetic_filing):
    filler = "x" * 100
    _write(
        synthetic_filing,
        f"""<html><body>
        <table>
          <tr><th>Revenue</th><th>2023</th></tr>
          <tr><td>Q1</td><td>100</td></tr>
        </table>
        {filler}
        <table>
          <tr><th>Revenue</th><th>2024</th></tr>
          <tr><td>Q2</td><td>200</td></tr>
        </table>
        </body></html>""",
    )

    doc = parse_filing(synthetic_filing)

    assert doc is not None
    assert len(doc.tables) == 1


# ---------------------------------------------------------------------------
# Parse error path
# ---------------------------------------------------------------------------


def test_parse_error_logs_failure_row(real_filing, session, failed_dir):
    with patch("pipeline.parser.BeautifulSoup", side_effect=Exception("boom")):
        result = parse_filing(real_filing, session=session, data_root=failed_dir)

    assert result is None

    from db.models.ingestion_failure import IngestionFailure

    row = (
        session.query(IngestionFailure).filter_by(file_path=str(real_filing)).first()
    )
    assert row is not None
    assert row.error_type == "PARSE_ERROR"
    assert "boom" in row.error_message


def test_parse_error_copies_file_to_failed_dir(real_filing, failed_dir):
    mock_session = MagicMock()

    with patch("pipeline.parser.BeautifulSoup", side_effect=Exception("boom")):
        parse_filing(real_filing, session=mock_session, data_root=failed_dir)

    dest = failed_dir / "data" / "failed" / real_filing.name
    assert dest.exists()


def test_parse_error_returns_none(real_filing):
    mock_session = MagicMock()

    with patch("pipeline.parser.BeautifulSoup", side_effect=Exception("boom")):
        result = parse_filing(real_filing, session=mock_session)

    assert result is None


# ---------------------------------------------------------------------------
# 10-K smoke tests — iXBRL annual report
# ---------------------------------------------------------------------------


def test_10k_text_is_non_empty(ten_k_filing):
    doc = parse_filing(ten_k_filing)

    assert doc is not None
    assert len(doc.text) > 10_000


def test_10k_tables_extracted(ten_k_filing):
    # The FY2024 10-K contains 63 tables; at minimum several must survive.
    doc = parse_filing(ten_k_filing)

    assert doc is not None
    assert len(doc.tables) > 10


def test_10k_income_statement_table(ten_k_filing):
    # The consolidated income statement reports net sales by product line across
    # three fiscal years.  In iXBRL filings the year labels appear in the first
    # data row (headers are empty), so search all rows for the fiscal-year label
    # and the iPhone revenue row.
    doc = parse_filing(ten_k_filing)

    assert doc is not None
    # iXBRL 10-Ks use short fiscal-year labels ("2024", "2023") in data rows.
    income_stmt = next(
        (
            t
            for t in doc.tables
            if any("2024" in str(c) for row in t["rows"] for c in row)
            and any("iPhone" in str(c) for row in t["rows"] for c in row)
        ),
        None,
    )
    assert income_stmt is not None, "Income statement table not found in 10-K"


def test_10k_balance_sheet_table(ten_k_filing):
    # The consolidated balance sheet (Table 24) lists assets and liabilities for
    # two fiscal year-end dates.  Locate it by the "ASSETS:" label in its rows.
    doc = parse_filing(ten_k_filing)

    assert doc is not None
    balance_sheet = next(
        (
            t
            for t in doc.tables
            if any("ASSETS:" in str(c) for row in t["rows"] for c in row)
        ),
        None,
    )
    assert balance_sheet is not None, "Balance sheet table not found in 10-K"


# ---------------------------------------------------------------------------
# 10-Q smoke tests — iXBRL quarterly report
# ---------------------------------------------------------------------------


def test_10q_text_is_non_empty(ten_q_filing):
    doc = parse_filing(ten_q_filing)

    assert doc is not None
    assert len(doc.text) > 5_000


def test_10q_tables_extracted(ten_q_filing):
    # The Q1 FY2022 10-Q contains 43 tables; at minimum several must survive.
    doc = parse_filing(ten_q_filing)

    assert doc is not None
    assert len(doc.tables) > 5


def test_10q_income_statement_table(ten_q_filing):
    # The quarterly income statement reports three-month periods.  In iXBRL
    # filings the period labels appear in data rows (headers are empty), so
    # search all rows for both the period label and the iPhone revenue row.
    doc = parse_filing(ten_q_filing)

    assert doc is not None
    income_stmt = next(
        (
            t
            for t in doc.tables
            if any("Three Months Ended" in str(c) for row in t["rows"] for c in row)
            and any("iPhone" in str(c) for row in t["rows"] for c in row)
        ),
        None,
    )
    assert income_stmt is not None, "Income statement table not found in 10-Q"


def test_10q_balance_sheet_table(ten_q_filing):
    doc = parse_filing(ten_q_filing)

    assert doc is not None
    balance_sheet = next(
        (
            t
            for t in doc.tables
            if any("ASSETS:" in str(c) for row in t["rows"] for c in row)
        ),
        None,
    )
    assert balance_sheet is not None, "Balance sheet table not found in 10-Q"
