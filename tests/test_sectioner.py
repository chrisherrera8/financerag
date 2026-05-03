"""Tests for pipeline.sectioner — SEC filing section boundary detection.

Real-file tests use fixture copies so originals in data/ are never touched.
Synthetic HTML is used only for edge cases that cannot be reliably targeted
in real filings (TOC dedup, adjacent-cell assembly, plain-text fallback).
"""
from pathlib import Path

import pytest

from pipeline.sectioner import Section, split_sections

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Apple FY2024 10-K — modern iXBRL, bold <span style="font-weight:700"> headers.
_APPLE_10K = _REPO_ROOT / "data/apple/10-K/0000320193-24-000123/aapl-20240928.htm"

# Google FY2015 10-K — legacy filing, bold <font style="font-weight:bold"> headers.
_GOOG_LEGACY_10K = (
    _REPO_ROOT / "data/alphabet/10-K/0001652044-16-000012/goog10-k2015.htm"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def apple_10k_html() -> str:
    """Raw HTML of the Apple FY2024 10-K, read once for the module."""
    return _APPLE_10K.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def apple_10k_sections(apple_10k_html) -> list[Section]:
    return split_sections(apple_10k_html)


@pytest.fixture(scope="module")
def goog_legacy_html() -> str:
    """Raw HTML of the Google FY2015 10-K, read once for the module."""
    return _GOOG_LEGACY_10K.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def goog_legacy_sections(goog_legacy_html) -> list[Section]:
    return split_sections(goog_legacy_html)


@pytest.fixture()
def synthetic_filing(tmp_path) -> Path:
    """Writable path inside tmp_path for tests that build their own HTML."""
    return tmp_path / "filing.htm"


# ---------------------------------------------------------------------------
# Modern iXBRL format (Apple 10-K) — bold <span style="font-weight:700">
# ---------------------------------------------------------------------------


def test_modern_xbrl_item1_business_detected(apple_10k_sections):
    names = [s.section_name for s in apple_10k_sections]
    assert "Item 1. Business" in names


def test_modern_xbrl_part_header_detected(apple_10k_sections):
    names = [s.section_name for s in apple_10k_sections]
    assert any("PART I" in n or "Part I" in n for n in names)


def test_modern_xbrl_item_letter_suffix_1a(apple_10k_sections):
    # Item 1A. is the canonical letter-suffix case in every 10-K.
    names = [s.section_name for s in apple_10k_sections]
    assert "Item 1A. Risk Factors" in names


def test_modern_xbrl_item_letter_suffix_7a(apple_10k_sections):
    names = [s.section_name for s in apple_10k_sections]
    assert "Item 7A. Quantitative and Qualitative Disclosures About Market Risk" in names


def test_modern_xbrl_item_double_letter_suffix_1c(apple_10k_sections):
    # Item 1C. Cybersecurity first appeared in 2023 disclosures — confirms
    # arbitrary-letter suffix parsing works beyond A/B.
    names = [s.section_name for s in apple_10k_sections]
    assert "Item 1C. Cybersecurity" in names


def test_modern_xbrl_item1_section_has_content(apple_10k_sections):
    item1 = next(s for s in apple_10k_sections if s.section_name == "Item 1. Business")
    assert len(item1.text) > 100


def test_modern_xbrl_other_preamble_present(apple_10k_sections):
    # Content exists before the first Item/Part header in the Apple 10-K.
    assert apple_10k_sections[0].section_name == "Other"
    assert len(apple_10k_sections[0].text) > 0


def test_modern_xbrl_section_order_starts_at_one(apple_10k_sections):
    assert apple_10k_sections[0].section_order == 1


def test_modern_xbrl_section_order_is_contiguous(apple_10k_sections):
    orders = [s.section_order for s in apple_10k_sections]
    assert orders == list(range(1, len(apple_10k_sections) + 1))


def test_modern_xbrl_multiple_items_detected(apple_10k_sections):
    item_sections = [s for s in apple_10k_sections if s.section_name.startswith("Item")]
    assert len(item_sections) >= 10


# ---------------------------------------------------------------------------
# Legacy format (Google FY2015 10-K) — bold <font style="font-weight:bold">
# with adjacent-cell title assembly (<td>ITEM 1.</td><td>BUSINESS</td>)
# ---------------------------------------------------------------------------


def test_legacy_part_i_detected(goog_legacy_sections):
    names = [s.section_name for s in goog_legacy_sections]
    assert "PART I" in names


def test_legacy_part_ii_detected(goog_legacy_sections):
    names = [s.section_name for s in goog_legacy_sections]
    assert "PART II" in names


def test_legacy_item_1_with_title_assembled(goog_legacy_sections):
    # Adjacent-cell assembly: ITEM 1. + BUSINESS → "ITEM 1. BUSINESS"
    names = [s.section_name for s in goog_legacy_sections]
    assert "ITEM 1. BUSINESS" in names


def test_legacy_item_1a_with_title_assembled(goog_legacy_sections):
    names = [s.section_name for s in goog_legacy_sections]
    assert "ITEM 1A. RISK FACTORS" in names


def test_legacy_item_1b_with_title_assembled(goog_legacy_sections):
    names = [s.section_name for s in goog_legacy_sections]
    assert "ITEM 1B. UNRESOLVED STAFF COMMENTS" in names


def test_legacy_item_7a_with_title_assembled(goog_legacy_sections):
    names = [s.section_name for s in goog_legacy_sections]
    assert "ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK" in names


def test_legacy_section_order_is_contiguous(goog_legacy_sections):
    orders = [s.section_order for s in goog_legacy_sections]
    assert orders == list(range(1, len(goog_legacy_sections) + 1))


def test_legacy_multiple_items_detected(goog_legacy_sections):
    item_sections = [s for s in goog_legacy_sections if s.section_name.startswith("ITEM")]
    assert len(item_sections) >= 5


# ---------------------------------------------------------------------------
# TOC deduplication — synthetic (behavior cannot be isolated in real filings)
# ---------------------------------------------------------------------------


def test_toc_href_link_does_not_create_duplicate_section(tmp_path):
    path = tmp_path / "filing.htm"
    path.write_text(
        "<html><body>"
        '<a href="#item1"><b>Item 1. Business</b></a>'
        "<p>Table of contents entry above.</p>"
        "<b>Item 1. Business</b>"
        "<p>Actual body content.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    html = path.read_text(encoding="utf-8")

    sections = split_sections(html)

    item1_sections = [s for s in sections if s.section_name == "Item 1. Business"]
    assert len(item1_sections) == 1


def test_toc_href_bare_text_skipped(tmp_path):
    path = tmp_path / "filing.htm"
    path.write_text(
        "<html><body>"
        '<a href="#part2">PART II</a>'
        "<p>TOC entry.</p>"
        '<span style="font-weight:700">PART II</span>'
        "<p>Actual part two body.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    html = path.read_text(encoding="utf-8")

    sections = split_sections(html)

    part2_sections = [s for s in sections if s.section_name == "PART II"]
    assert len(part2_sections) == 1


# ---------------------------------------------------------------------------
# Fallback plain-text detection — synthetic (requires no bold markup at all)
# ---------------------------------------------------------------------------


def test_fallback_detects_items_when_no_bold_present(tmp_path):
    path = tmp_path / "filing.htm"
    path.write_text(
        "<html><body>"
        "<p>Item 1. Business</p>"
        "<p>Business content.</p>"
        "<p>Item 2. Properties</p>"
        "<p>Property content.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    html = path.read_text(encoding="utf-8")

    sections = split_sections(html)

    names = [s.section_name for s in sections]
    assert "Item 1. Business" in names
    assert "Item 2. Properties" in names


# ---------------------------------------------------------------------------
# Section dataclass shape
# ---------------------------------------------------------------------------


def test_section_dataclass_has_required_fields(apple_10k_sections):
    s = apple_10k_sections[0]
    assert isinstance(s.section_name, str)
    assert isinstance(s.section_order, int)
    assert isinstance(s.text, str)
