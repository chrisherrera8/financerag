"""Split a paragraph-level Chunk into sentence-level Chunk objects."""

import re

import tiktoken

from pipeline.chunker import Chunk

_ENC = tiktoken.get_encoding("cl100k_base")
_SENTENCE_MIN_TOKENS = 5
_NOTES_SECTION = "Notes to Financial Statements"

# Matches footnote lines: leading digit(s)+space or leading asterisk+space
_FOOTNOTE_RE = re.compile(r"^(\d+\s|\*\s)")

# Sentence boundary: split on ". ", "! ", "? " or end-of-string after punctuation
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _tokens(text: str) -> int:
    return len(_ENC.encode(text))


def _split_into_sentences(text: str) -> list[str]:
    """Split *text* into a list of sentence strings."""
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _make_sentence_chunks(
    sentences: list[str],
    section_name: str,
    section_order: int | None,
    parent_text: str,
) -> list[Chunk]:
    """Build sentence-level Chunk objects, discarding fragments below the token minimum."""
    chunks = []
    for sentence in sentences:
        tok = _tokens(sentence)
        if tok < _SENTENCE_MIN_TOKENS:
            continue
        chunks.append(Chunk(
            text=sentence,
            chunk_level="sentence",
            token_count=tok,
            section_name=section_name,
            section_order=section_order,
            parent_paragraph_text=parent_text,
        ))
    return chunks


def split_sentences(chunk: Chunk) -> list[Chunk]:
    """Split a paragraph-level *chunk* into sentence-level Chunk objects.

    Sentences with fewer than ``_SENTENCE_MIN_TOKENS`` tokens are discarded as fragments. Lines that
    match a footnote pattern (leading digit or ``*``) are rerouted to
    ``"Notes to Financial Statements"`` regardless of the parent section.

    Args:
        chunk: A paragraph-level Chunk to split.

    Returns:
        Ordered list of sentence-level Chunk objects with token counts set and
        fragments removed.
    """
    lines = chunk.text.splitlines()
    footnote_lines: list[str] = []
    prose_lines: list[str] = []

    for line in lines:
        if _FOOTNOTE_RE.match(line.strip()):
            footnote_lines.append(line.strip())
        else:
            prose_lines.append(line.strip())

    prose_text = " ".join(prose_lines).strip()

    results = _make_sentence_chunks(
        _split_into_sentences(prose_text),
        chunk.section_name,
        chunk.section_order,
        chunk.text,
    )
    # section_order is unknown for footnotes; the full-document segmentation pass must
    # backfill this from the Notes section's actual order.
    results += _make_sentence_chunks(
        footnote_lines,
        _NOTES_SECTION,
        None,
        chunk.text,
    )

    return results
