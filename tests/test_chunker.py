"""Tests for pipeline.chunker — token-bounded paragraph chunking with overlap.

Detection format contracts (documented to avoid silent drift):
  - Tables: lines where most lines match '| ... |' pipe-delimited format
  - Lists: lines where most lines start with '- ' bullet prefix

Synthetic section text is used throughout; assertions target observable
behaviour (token bounds, shared overlap tokens, item boundaries) rather than
implementation details such as exact sentence extraction logic.
"""

import pytest
import tiktoken

from pipeline.chunker import Chunk, _split_at_sentence_boundary, chunk_section
from pipeline.sectioner import Section

_ENC = tiktoken.get_encoding("cl100k_base")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tokens(text: str) -> int:
    return len(_ENC.encode(text))


def _sentence(n_words: int = 15) -> str:
    """Return one sentence of approximately *n_words* common-word tokens."""
    vocab = [
        "the", "quick", "brown", "fox", "jumps", "over", "the", "lazy",
        "dog", "and", "then", "runs", "back", "home", "again",
    ]
    words = (vocab * ((n_words // len(vocab)) + 1))[:n_words]
    return " ".join(words) + "."


def _paragraph(target_tokens: int) -> str:
    """Return a paragraph whose token count is at least *target_tokens*."""
    sentences, total = [], 0
    while total < target_tokens:
        s = _sentence(15)
        sentences.append(s)
        total += _tokens(s)
    return " ".join(sentences)


def _section(text: str, name: str = "Item 1. Business", order: int = 1) -> Section:
    return Section(section_name=name, section_order=order, text=text)


def _table_row(n_cols: int = 4) -> str:
    return "| " + " | ".join(["word cell value"] * n_cols) + " |"


def _table(n_rows: int, n_cols: int = 4) -> str:
    header = _table_row(n_cols)
    separator = "| " + " | ".join(["---"] * n_cols) + " |"
    rows = [_table_row(n_cols) for _ in range(n_rows)]
    return "\n".join([header, separator] + rows)


def _list_block(n_items: int, words_per_item: int = 10) -> str:
    return "\n".join(f"- {_sentence(words_per_item)}" for _ in range(n_items))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def two_normal_paragraphs() -> Section:
    # Two paragraphs each well inside the 200–400 token target band.
    p1 = _paragraph(280)
    p2 = _paragraph(280)
    return _section(p1 + "\n\n" + p2)


@pytest.fixture()
def overflow_section() -> Section:
    # Single paragraph at 700 tokens — forces at least two overflow splits.
    return _section(_paragraph(700))


@pytest.fixture()
def undersize_then_normal() -> Section:
    # ~6-token leading paragraph — must merge with the following paragraph.
    return _section("This is a short paragraph." + "\n\n" + _paragraph(280))


@pytest.fixture()
def normal_then_undersize() -> Section:
    # ~3-token trailing paragraph — must merge with the preceding paragraph.
    return _section(_paragraph(250) + "\n\n" + "End note.")


@pytest.fixture()
def table_under_cap() -> Section:
    tbl = _table(n_rows=10)
    assert _tokens(tbl) < 800, "fixture assumption violated"
    return _section(tbl)


@pytest.fixture()
def table_over_cap() -> Section:
    tbl = _table(n_rows=80, n_cols=6)
    assert _tokens(tbl) > 800, "fixture assumption violated"
    return _section(tbl)


@pytest.fixture()
def short_list() -> Section:
    lst = _list_block(n_items=5, words_per_item=8)
    assert _tokens(lst) < 400, "fixture assumption violated"
    return _section(lst)


@pytest.fixture()
def long_list() -> Section:
    lst = _list_block(n_items=40, words_per_item=15)
    assert _tokens(lst) > 400, "fixture assumption violated"
    return _section(lst)


# ---------------------------------------------------------------------------
# Chunk dataclass shape
# ---------------------------------------------------------------------------


def test_chunk_has_required_fields(two_normal_paragraphs):
    chunks = chunk_section(two_normal_paragraphs)
    assert chunks
    c = chunks[0]
    assert isinstance(c.text, str)
    assert c.chunk_level == "paragraph"
    assert isinstance(c.token_count, int)
    assert isinstance(c.section_name, str)
    assert isinstance(c.section_order, int)


def test_token_count_matches_text(two_normal_paragraphs):
    chunks = chunk_section(two_normal_paragraphs)
    for chunk in chunks:
        assert chunk.token_count == _tokens(chunk.text)


def test_section_metadata_propagated_to_all_chunks():
    text = _paragraph(280) + "\n\n" + _paragraph(280)
    sec = _section(text, name="Item 7. MD&A", order=5)
    chunks = chunk_section(sec)
    for chunk in chunks:
        assert chunk.section_name == "Item 7. MD&A"
        assert chunk.section_order == 5


# ---------------------------------------------------------------------------
# Normal split (paragraphs already within 200–400 token target)
# ---------------------------------------------------------------------------


def test_normal_split_produces_at_least_two_chunks(two_normal_paragraphs):
    chunks = chunk_section(two_normal_paragraphs)
    assert len(chunks) >= 2


def test_normal_chunks_within_400_token_cap(two_normal_paragraphs):
    chunks = chunk_section(two_normal_paragraphs)
    for chunk in chunks:
        assert chunk.token_count <= 400


# ---------------------------------------------------------------------------
# Overflow split (single paragraph > 400 tokens)
# ---------------------------------------------------------------------------


def test_overflow_paragraph_split_into_multiple_chunks(overflow_section):
    chunks = chunk_section(overflow_section)
    assert len(chunks) >= 2


def test_overflow_chunks_within_400_token_cap(overflow_section):
    chunks = chunk_section(overflow_section)
    for chunk in chunks:
        assert chunk.token_count <= 400, f"chunk has {chunk.token_count} tokens"


def test_overflow_chunks_end_at_sentence_boundary(overflow_section):
    # Every non-final chunk must end with a period — never mid-sentence.
    chunks = chunk_section(overflow_section)
    for chunk in chunks[:-1]:
        assert chunk.text.rstrip().endswith("."), (
            f"mid-stream chunk does not end at sentence boundary: ...{chunk.text[-40:]!r}"
        )


# ---------------------------------------------------------------------------
# Undersize merge (< 50 tokens merges with adjacent paragraph)
# ---------------------------------------------------------------------------


def test_tiny_leading_paragraph_merged_with_next(undersize_then_normal):
    chunks = chunk_section(undersize_then_normal)
    assert len(chunks) == 1


def test_merged_chunk_contains_tiny_leading_text(undersize_then_normal):
    chunks = chunk_section(undersize_then_normal)
    combined = " ".join(c.text for c in chunks)
    assert "This is a short paragraph." in combined


def test_tiny_trailing_paragraph_merged_with_previous(normal_then_undersize):
    chunks = chunk_section(normal_then_undersize)
    assert len(chunks) == 1


def test_merged_chunk_contains_tiny_trailing_text(normal_then_undersize):
    chunks = chunk_section(normal_then_undersize)
    combined = " ".join(c.text for c in chunks)
    assert "End note." in combined


# ---------------------------------------------------------------------------
# Overlap carry (last sentence of chunk N appears at start of chunk N+1)
#
# Rather than extracting sentence boundaries in the test (which would couple
# the test to the implementation's splitting logic), we check that the opening
# tokens of chunk N+1 were also present near the end of chunk N.
# ---------------------------------------------------------------------------


def test_overlap_opening_of_next_chunk_is_in_previous_chunk(two_normal_paragraphs):
    chunks = chunk_section(two_normal_paragraphs)
    assert len(chunks) >= 2
    # The first ~50 characters of chunk[1] must appear verbatim inside chunk[0].
    overlap_prefix = chunks[1].text[:50]
    assert overlap_prefix in chunks[0].text, (
        f"overlap prefix not found in previous chunk: {overlap_prefix!r}"
    )


def test_overlap_does_not_push_chunk_over_400_tokens(two_normal_paragraphs):
    chunks = chunk_section(two_normal_paragraphs)
    assert len(chunks) >= 2
    assert chunks[1].token_count <= 400


# ---------------------------------------------------------------------------
# Table handling (pipe-delimited '| ... |' format)
# ---------------------------------------------------------------------------


def test_table_under_800_tokens_is_single_chunk(table_under_cap):
    chunks = chunk_section(table_under_cap)
    assert len(chunks) == 1


def test_table_over_800_tokens_is_split(table_over_cap):
    chunks = chunk_section(table_over_cap)
    assert len(chunks) >= 2


def test_table_chunks_within_800_token_hard_cap(table_over_cap):
    chunks = chunk_section(table_over_cap)
    for chunk in chunks:
        assert chunk.token_count <= 800, f"table chunk exceeds 800-token cap: {chunk.token_count}"


def test_table_chunk_level_is_paragraph(table_under_cap):
    chunks = chunk_section(table_under_cap)
    for chunk in chunks:
        assert chunk.chunk_level == "paragraph"


# ---------------------------------------------------------------------------
# List handling ('- ' bullet prefix format)
# ---------------------------------------------------------------------------


def test_short_list_kept_as_single_chunk(short_list):
    chunks = chunk_section(short_list)
    assert len(chunks) == 1


def test_long_list_split_into_multiple_chunks(long_list):
    chunks = chunk_section(long_list)
    assert len(chunks) >= 2


def test_long_list_chunks_within_400_token_cap(long_list):
    chunks = chunk_section(long_list)
    for chunk in chunks:
        assert chunk.token_count <= 400


# ---------------------------------------------------------------------------
# Overflow split — no word duplication at chunk boundaries (regression)
# ---------------------------------------------------------------------------


def test_overflow_no_word_duplicated_at_sentence_boundary_split():
    # Paragraph with clear sentence boundaries that forces a sentence-boundary split.
    # Before the bug fix, the overflow word appeared twice in the tail chunk.
    text = (
        "Revenue rose in Q1. "
        "Costs fell sharply across all divisions. "
        + " ".join([f"term{i}" for i in range(400)]) + "."  # long sentence to force overflow
    )
    sec = _section(text)
    chunks = chunk_section(sec)
    for chunk in chunks:
        words = chunk.text.split()
        for i in range(len(words) - 1):
            assert not (words[i] == words[i + 1] and words[i] not in {"the", "and", "of"}), (
                f"duplicate adjacent word {words[i]!r} found in chunk — possible boundary duplication"
            )


def test_overflow_no_word_duplicated_at_hard_word_split():
    # Single run of unique words with no periods — forces a hard word-boundary split.
    # Before the bug fix, the split word appeared twice in the tail chunk.
    unique_words = [f"word{i}" for i in range(120)]
    text = " ".join(unique_words)
    sec = _section(text)
    chunks = chunk_section(sec)
    all_words = [w for chunk in chunks for w in chunk.text.split()]
    # Every unique word should appear exactly once across all chunks (overlap excluded
    # for hard-split prose, which carries no sentence overlap).
    assert len(all_words) == len(set(all_words)), (
        "duplicate words found across chunks — boundary word was emitted twice"
    )


# ---------------------------------------------------------------------------
# _merge_undersize must not push a merged chunk past the 400-token cap
# ---------------------------------------------------------------------------


def test_merge_undersize_does_not_exceed_400_token_cap():
    # Construct two adjacent paragraphs: a large one just below the cap and a
    # tiny undersize one. _merge_undersize must not blindly join them when the
    # result would exceed _PARAGRAPH_TARGET_MAX (400 tokens).
    big_paragraph = _paragraph(390)
    assert 350 <= _tokens(big_paragraph) <= 400, "fixture assumption violated"

    tiny_paragraph = "Short note."
    assert _tokens(tiny_paragraph) < 50, "fixture assumption violated"

    text = big_paragraph + "\n\n" + tiny_paragraph
    sec = _section(text)

    chunks = chunk_section(sec)

    for chunk in chunks:
        assert chunk.token_count <= 400, (
            f"_merge_undersize produced a {chunk.token_count}-token chunk, "
            "violating the 400-token cap"
        )


def test_long_list_chunks_start_at_item_boundary(long_list):
    chunks = chunk_section(long_list)
    for chunk in chunks:
        first_line = chunk.text.splitlines()[0]
        assert first_line.startswith("- "), (
            f"list chunk does not start at item boundary: {first_line!r}"
        )


@pytest.mark.parametrize("text", [None, "", "   "])
def test_chunk_section_returns_empty_list_for_blank_text(text):
    sec = Section(section_name="Item 1. Business", section_order=1, text=text)
    assert chunk_section(sec) == []


# ---------------------------------------------------------------------------
# _add_overlap must not push chunk over the 400-token cap (regression)
# ---------------------------------------------------------------------------


def test_add_overlap_skipped_when_chunk_already_at_cap():
    # p1: a normal paragraph (all period-terminated sentences so _last_sentence
    #     extracts the final ~16-token sentence as the overlap candidate).
    # p2: _paragraph(385) builds until token count >= 385; with 16-token sentences
    #     this lands at exactly 400 tokens — right at the cap, so _split_paragraph_overflow
    #     leaves it unsplit.  Adding a 16-token overlap sentence would produce ~416 tokens,
    #     so _add_overlap must skip overlap entirely and leave p2 unchanged.
    p1 = _paragraph(200)
    p2 = _paragraph(385)

    assert _tokens(p2) == 400, "p2 fixture assumption violated: expected exactly 400 tokens"

    sec = _section(p1 + "\n\n" + p2)
    chunks = chunk_section(sec)

    # The cap must not be breached.
    for chunk in chunks:
        assert chunk.token_count <= 400, (
            f"_add_overlap produced a {chunk.token_count}-token chunk, "
            "violating the 400-token cap"
        )

    # The at-cap chunk must not have been prefixed with an overlap sentence —
    # verify its text matches p2 verbatim (overlap was skipped, not truncated).
    at_cap_chunks = [c for c in chunks if c.token_count == 400]
    assert at_cap_chunks, "expected at least one chunk at exactly 400 tokens"
    assert at_cap_chunks[0].text == p2, (
        "expected _add_overlap to skip overlap entirely when chunk is already at the cap"
    )

