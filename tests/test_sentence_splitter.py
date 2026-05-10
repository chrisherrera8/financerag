"""Tests for pipeline.sentence_splitter — sentence-level chunking."""

import pytest
import tiktoken

from pipeline.sentence_splitter import split_sentences


def test_split_produces_multiple_chunks(make_paragraph_chunk):
    para = make_paragraph_chunk(
        "The company reported strong earnings. Revenue grew by fifteen percent year over year. "
        "Management expects continued growth in the next fiscal quarter ahead."
    )
    results = split_sentences(para)

    assert len(results) >= 2


def test_split_chunks_have_sentence_level(make_paragraph_chunk):
    para = make_paragraph_chunk(
        "The company reported strong earnings. Revenue grew by fifteen percent year over year. "
        "Management expects continued growth in the next fiscal quarter ahead."
    )
    results = split_sentences(para)

    for chunk in results:
        assert chunk.chunk_level == "sentence"


def test_split_inherits_section_metadata(make_paragraph_chunk):
    para = make_paragraph_chunk(
        "Net income increased substantially this year. Operating expenses remained flat.",
        section_name="Management Discussion",
        section_order=3,
    )
    results = split_sentences(para)

    assert len(results) >= 1, "sentences are long enough to survive fragment discard"
    for chunk in results:
        assert chunk.section_name == "Management Discussion"
        assert chunk.section_order == 3


def test_split_sets_parent_paragraph_text(make_paragraph_chunk):
    para = make_paragraph_chunk(
        "Revenue increased this year over last year. Costs were also higher than expected."
    )
    results = split_sentences(para)

    for chunk in results:
        assert chunk.parent_paragraph_text == para.text


def test_split_sets_token_count_on_each_sentence(make_paragraph_chunk):
    para = make_paragraph_chunk(
        "The board approved the annual dividend payment to shareholders. "
        "Earnings per share rose to three dollars and forty-two cents."
    )
    results = split_sentences(para)

    for chunk in results:
        assert chunk.token_count > 0


def test_fragment_below_10_tokens_is_discarded(make_paragraph_chunk):
    para = make_paragraph_chunk(
        "The company experienced significant growth in international markets during fiscal year. "
        "See above."
    )
    results = split_sentences(para)

    texts = [c.text for c in results]
    assert not any("See above" in t for t in texts)
    assert any("international markets" in t for t in texts)


def test_fragment_exactly_9_tokens_is_discarded(make_paragraph_chunk):
    enc = tiktoken.get_encoding("cl100k_base")

    # "See above." = 3 cl100k_base tokens — verified offline; assert is a canary, not discovery
    FRAGMENT = "See above."
    assert len(enc.encode(FRAGMENT)) < 10

    long_sent = (
        "The company reported record revenues for the fiscal year ended December thirty-first. "
    )
    para = make_paragraph_chunk(long_sent + FRAGMENT)
    results = split_sentences(para)

    assert all(c.token_count >= 10 for c in results)


def test_all_fragments_returns_empty_list(make_paragraph_chunk):
    para = make_paragraph_chunk("Ok. Yes. No.")
    results = split_sentences(para)

    assert results == []


@pytest.mark.parametrize(
    "footnote_text",
    [
        "1 This amount excludes the fair value adjustment for derivatives.",
        "* Certain prior-period amounts have been reclassified to conform.",
        "42 See Note 7 for additional details regarding the pension obligation.",
    ],
)
def test_footnote_is_rerouted_to_notes_section(footnote_text, make_paragraph_chunk):
    long_body = (
        "Total assets increased to one hundred and twenty billion dollars this year. "
        "The increase reflects acquisitions completed during the fiscal period."
    )
    para = make_paragraph_chunk(long_body + "\n" + footnote_text)
    results = split_sentences(para)

    footnote_chunks = [c for c in results if footnote_text.strip() in c.text]
    assert len(footnote_chunks) == 1, "footnote must be present as a rerouted chunk, not silently dropped"
    assert footnote_chunks[0].section_name == "Notes to Financial Statements"


def test_footnote_section_order_is_none(make_paragraph_chunk):
    long_body = (
        "Total assets increased to one hundred and twenty billion dollars this year. "
        "The increase reflects acquisitions completed during the fiscal period."
    )
    footnote = "1 See Note 7 for additional details regarding the pension obligation."
    para = make_paragraph_chunk(long_body + "\n" + footnote, section_order=3)
    results = split_sentences(para)

    footnote_chunks = [c for c in results if c.section_name == "Notes to Financial Statements"]
    assert len(footnote_chunks) == 1
    assert footnote_chunks[0].section_order is None


def test_prose_line_with_leading_whitespace_is_not_double_spaced(make_paragraph_chunk):
    para = make_paragraph_chunk(
        "Revenue increased twelve percent and\n"
        "  operating expenses remained flat compared to last fiscal year."
    )
    results = split_sentences(para)

    prose_texts = [c.text for c in results if c.section_name != "Notes to Financial Statements"]
    assert len(prose_texts) == 1, "two continuation lines should produce one sentence chunk"
    assert "  " not in prose_texts[0], (
        f"double space inside chunk — prose line leading whitespace was not stripped: {prose_texts[0]!r}"
    )


def test_non_footnote_line_not_rerouted(make_paragraph_chunk):
    para = make_paragraph_chunk(
        "Revenue for the period was twelve billion dollars in total. "
        "Operating income grew by eight percent compared with prior year results."
    )
    results = split_sentences(para)

    for chunk in results:
        assert chunk.section_name != "Notes to Financial Statements"
