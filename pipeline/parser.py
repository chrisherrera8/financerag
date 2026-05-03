import logging
import shutil
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from sqlalchemy.orm import Session

from db.models.ingestion_failure import IngestionFailure

"""Parse raw SEC HTML filings into clean, structured text and table data."""

logger = logging.getLogger(__name__)

_BOILERPLATE_TAGS = {"script", "style", "nav", "header", "footer"}


@dataclass
class ParsedDocument:
    """Structured output of a parsed SEC filing.

    Attributes:
        text: Plain text of the filing with boilerplate removed and headings preserved.
        tables: List of extracted tables, each a dict with ``headers`` (list of str)
            and ``rows`` (list of list of str). Multi-page continuation tables are
            stitched into a single entry.
    """

    text: str
    tables: list[dict] = field(default_factory=list)


def _extract_tables(soup: BeautifulSoup) -> list[dict]:
    """Return a raw table list from *soup*, including a ``_src`` key for gap measurement."""
    tables = []
    for tbl in soup.find_all("table"):
        rows_el = tbl.find_all("tr")
        if not rows_el:
            continue
        headers = [th.get_text(strip=True) for th in rows_el[0].find_all(["th", "td"])]
        rows = [
            [td.get_text(strip=True) for td in tr.find_all(["th", "td"])]
            for tr in rows_el[1:]
        ]
        tables.append({"headers": headers, "rows": rows, "_src": str(tbl)})
    return tables


def _header_overlap(a: list[str], b: list[str]) -> float:
    """Return the Jaccard-style overlap ratio between two header lists (case-insensitive)."""
    if not a or not b:
        return 0.0
    set_a = {h.lower() for h in a}
    set_b = {h.lower() for h in b}
    return len(set_a & set_b) / max(len(set_a), len(set_b))


def _stitch_tables(raw_tables: list[dict], html_source: str) -> list[dict]:
    """Merge multi-page continuation tables (OQ-04).

    Two adjacent tables are stitched when both conditions hold:
    - The stripped HTML between them is ≤ 500 characters.
    - At least 50% of column headers (by Jaccard overlap) match.
    """
    if not raw_tables:
        return raw_tables

    # Locate each table's start/end offset in the raw HTML.
    src_positions: list[tuple[int, int]] = []
    search_from = 0
    for tbl in raw_tables:
        snippet = tbl["_src"]
        start = html_source.find(snippet, search_from)
        if start == -1:
            start = search_from
        end = start + len(snippet)
        src_positions.append((start, end))
        search_from = end

    result: list[dict] = []
    i = 0
    while i < len(raw_tables):
        current = {k: v for k, v in raw_tables[i].items() if k != "_src"}
        current["rows"] = list(current["rows"])
        while i + 1 < len(raw_tables):
            between = html_source[src_positions[i][1] : src_positions[i + 1][0]]
            gap = len(between.strip())
            overlap = _header_overlap(current["headers"], raw_tables[i + 1]["headers"])
            if gap <= 500 and overlap >= 0.5:
                current["rows"].extend(raw_tables[i + 1]["rows"])
                src_positions[i] = (src_positions[i][0], src_positions[i + 1][1])
                i += 1
            else:
                break
        result.append(current)
        i += 1
    return result


def parse_filing(
    file_path: Path,
    session: Session | None = None,
    data_root: Path | None = None,
) -> ParsedDocument | None:
    """Parse a single SEC HTML filing into a :class:`ParsedDocument`.

    Args:
        file_path: Path to the ``.htm`` filing on disk.
        session: Optional SQLAlchemy session. When provided, parse failures are
            persisted to ``ingestion_failures`` as a ``PARSE_ERROR`` row.
        data_root: Root directory used to resolve ``data/failed/``. Defaults to
            the current working directory when ``None``.

    Returns:
        A :class:`ParsedDocument` on success, or ``None`` if parsing fails.
        The caller should treat ``None`` as a signal to skip this file.
    """
    try:
        html = file_path.read_text(encoding="utf-8", errors="replace")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(html, "lxml")

        for tag in soup.find_all(_BOILERPLATE_TAGS):
            tag.decompose()

        raw_tables = _extract_tables(soup)
        plain_text = soup.get_text(separator=" ", strip=True)
        # Use the BS4-serialized source for gap measurement so table _src strings
        # can be located reliably (lxml reformats the original HTML).
        serialized = str(soup)
        tables = _stitch_tables(raw_tables, serialized)

        logger.debug(
            "parsed %s: %d chars, %d raw tables → %d after stitching",
            file_path.name,
            len(plain_text),
            len(raw_tables),
            len(tables),
        )
        for i, tbl in enumerate(tables):
            logger.debug(
                "  table[%d]: headers=%s, %d rows\n    %s",
                i,
                tbl["headers"],
                len(tbl["rows"]),
                "\n    ".join(str(row) for row in tbl["rows"]),
            )

        return ParsedDocument(text=plain_text, tables=tables)

    except Exception as exc:
        msg = str(exc)
        logger.error("PARSE_ERROR %s: %s", file_path, msg)

        if session is not None:
            failure = IngestionFailure(
                file_path=str(file_path),
                error_type="PARSE_ERROR",
                error_message=msg,
            )
            session.add(failure)
            session.flush()

        if data_root is not None:
            dest_dir = data_root / "data" / "failed"
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest_dir / file_path.name)
        elif file_path.exists():
            dest_dir = Path("data") / "failed"
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, dest_dir / file_path.name)

        return None
