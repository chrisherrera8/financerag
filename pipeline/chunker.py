"""Split a Section's plain text into token-bounded paragraph-level Chunk objects."""

import re
from dataclasses import dataclass

import tiktoken

from pipeline.sectioner import Section

_ENC = tiktoken.get_encoding("cl100k_base")

_PARAGRAPH_MIN = 50
_PARAGRAPH_TARGET_MAX = 400
_TABLE_HARD_CAP = 800

# Matches a pipe-delimited table row: '| cell | cell |'
_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$")
# Matches a bullet list item: '- text' or '* text'
_LIST_ITEM_RE = re.compile(r"^\s*[-*]\s")


@dataclass
class Chunk:
    """A token-bounded text chunk derived from a single Section.

    Attributes:
        text: Plain text content of the chunk.
        chunk_level: Always ``"paragraph"`` for chunks produced by this module.
        token_count: Number of cl100k_base tokens in *text*.
        section_name: Inherited from the parent Section.
        section_order: Inherited from the parent Section.
    """

    text: str
    chunk_level: str = "paragraph"
    token_count: int = 0
    section_name: str = ""
    section_order: int = 0


def _tokens(text: str) -> int:
    """Return the cl100k_base token count for *text*."""
    return len(_ENC.encode(text))


def _last_sentence(text: str) -> str:
    """Return the last complete sentence from *text*, or empty string if none found.

    Returns empty string for blocks (tables, lists) that contain no period-terminated
    sentences, preventing unbounded overlap carry.
    """
    stripped = text.rstrip()
    idx = stripped.rfind(".", 0, len(stripped) - 1)
    if idx == -1:
        return ""
    return stripped[idx + 1:].strip()


def _split_at_sentence_boundary(text: str, max_tokens: int) -> tuple[str, str]:
    """Split *text* into (head, tail) where head is ≤ *max_tokens* tokens.

    The split point is the last sentence boundary (period) before the token cap.
    If no sentence boundary exists before the cap, a hard word-boundary split is used.
    """
    words = text.split()
    head_words: list[str] = []
    last_period_idx: int = -1

    for i, word in enumerate(words):
        head_words.append(word)
        if _tokens(" ".join(head_words)) > max_tokens:
            # Back off to the last sentence boundary
            if last_period_idx >= 0:
                head = " ".join(head_words[: last_period_idx + 1])
                tail = " ".join(head_words[last_period_idx + 1 :] + words[i + 1 :])
            else:
                # No sentence boundary found — split at the word before cap
                head = " ".join(head_words[:-1])
                tail = " ".join([head_words[-1]] + words[i + 1 :])
            return head.strip(), tail.strip()
        if word.endswith("."):
            last_period_idx = i

    return text.strip(), ""


def _is_table(block: str) -> bool:
    """Return True if the majority of non-empty lines look like pipe-table rows."""
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if not lines:
        return False
    table_lines = sum(1 for ln in lines if _TABLE_ROW_RE.match(ln))
    return table_lines / len(lines) >= 0.6


def _is_list(block: str) -> bool:
    """Return True if the majority of non-empty lines look like bullet list items."""
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if not lines:
        return False
    list_lines = sum(1 for ln in lines if _LIST_ITEM_RE.match(ln))
    return list_lines / len(lines) >= 0.6


def _chunk_table(block: str, section_name: str, section_order: int) -> list[Chunk]:
    """Split a pipe-delimited table into Chunk objects respecting the 800-token hard cap."""
    if _tokens(block) <= _TABLE_HARD_CAP:
        return [Chunk(text=block, token_count=_tokens(block),
                      section_name=section_name, section_order=section_order)]

    rows = block.splitlines()
    chunks: list[Chunk] = []
    current_rows: list[str] = []

    for row in rows:
        candidate = "\n".join(current_rows + [row])
        if _tokens(candidate) > _TABLE_HARD_CAP and current_rows:
            text = "\n".join(current_rows)
            chunks.append(Chunk(text=text, token_count=_tokens(text),
                                section_name=section_name, section_order=section_order))
            current_rows = [row]
        else:
            current_rows.append(row)

    if current_rows:
        text = "\n".join(current_rows)
        chunks.append(Chunk(text=text, token_count=_tokens(text),
                            section_name=section_name, section_order=section_order))

    return chunks


def _chunk_list(block: str, section_name: str, section_order: int) -> list[Chunk]:
    """Split a bullet list into Chunk objects at item boundaries."""
    if _tokens(block) <= _PARAGRAPH_TARGET_MAX:
        return [Chunk(text=block, token_count=_tokens(block),
                      section_name=section_name, section_order=section_order)]

    items = block.splitlines()
    chunks: list[Chunk] = []
    current_items: list[str] = []

    for item in items:
        candidate = "\n".join(current_items + [item])
        if _tokens(candidate) > _PARAGRAPH_TARGET_MAX and current_items:
            text = "\n".join(current_items)
            chunks.append(Chunk(text=text, token_count=_tokens(text),
                                section_name=section_name, section_order=section_order))
            current_items = [item]
        else:
            current_items.append(item)

    if current_items:
        text = "\n".join(current_items)
        chunks.append(Chunk(text=text, token_count=_tokens(text),
                            section_name=section_name, section_order=section_order))

    return chunks


def _chunk_paragraph(text: str, section_name: str, section_order: int) -> list[Chunk]:
    """Split a plain-text paragraph into ≤400-token Chunk objects at sentence boundaries."""
    chunks: list[Chunk] = []
    remaining = text.strip()

    while remaining:
        if _tokens(remaining) <= _PARAGRAPH_TARGET_MAX:
            chunks.append(Chunk(text=remaining, token_count=_tokens(remaining),
                                section_name=section_name, section_order=section_order))
            break
        head, tail = _split_at_sentence_boundary(remaining, _PARAGRAPH_TARGET_MAX)
        if not head:
            # Degenerate case: single word > cap; emit it and continue.
            head = remaining
            tail = ""
        chunks.append(Chunk(text=head, token_count=_tokens(head),
                            section_name=section_name, section_order=section_order))
        remaining = tail

    return chunks


def _merge_undersize(chunks: list[Chunk]) -> list[Chunk]:
    """Merge any Chunk whose token_count < _PARAGRAPH_MIN into an adjacent neighbour.

    Merges are skipped when the joined result would exceed _PARAGRAPH_TARGET_MAX.
    Each undersize chunk prefers the preceding neighbour; falls back to the following
    one when it is the first chunk. Metadata is always inherited from the earlier chunk.
    """
    merged: list[Chunk] = []
    i = 0
    while i < len(chunks):
        chunk = chunks[i]
        if chunk.token_count >= _PARAGRAPH_MIN:
            merged.append(chunk)
            i += 1
            continue

        if merged:
            prev = merged[-1]
            joined = prev.text + " " + chunk.text
            joined_tokens = _tokens(joined)
            if joined_tokens <= _PARAGRAPH_TARGET_MAX:
                merged[-1] = Chunk(
                    text=joined,
                    token_count=joined_tokens,
                    section_name=prev.section_name,
                    section_order=prev.section_order,
                )
                i += 1
                continue

        if i + 1 < len(chunks):
            nxt = chunks[i + 1]
            joined = chunk.text + " " + nxt.text
            joined_tokens = _tokens(joined)
            if joined_tokens <= _PARAGRAPH_TARGET_MAX:
                merged.append(Chunk(
                    text=joined,
                    token_count=joined_tokens,
                    section_name=chunk.section_name,
                    section_order=chunk.section_order,
                ))
                i += 2
                continue

        merged.append(chunk)
        i += 1
    return merged


def _add_overlap(chunks: list[Chunk]) -> list[Chunk]:
    """Prepend the last sentence of chunk N to the start of chunk N+1."""
    if len(chunks) < 2:
        return chunks

    result: list[Chunk] = [chunks[0]]
    for i in range(1, len(chunks)):
        overlap = _last_sentence(chunks[i - 1].text)
        if not overlap:
            result.append(chunks[i])
            continue
        new_text = overlap + " " + chunks[i].text
        if _tokens(new_text) > _PARAGRAPH_TARGET_MAX:
            result.append(chunks[i])
            continue
        result.append(Chunk(
            text=new_text,
            token_count=_tokens(new_text),
            section_name=chunks[i].section_name,
            section_order=chunks[i].section_order,
        ))
    return result


def chunk_section(section: Section) -> list[Chunk]:
    """Split *section* into paragraph-level :class:`Chunk` objects.

    Args:
        section: A :class:`~pipeline.sectioner.Section` with plain text content.

    Returns:
        Ordered list of :class:`Chunk` objects with token bounds applied,
        undersize paragraphs merged, and one sentence of overlap carried
        into each successive chunk.
    """
    if not section.text:
        return []

    name = section.section_name
    order = section.section_order

    # Split text into blocks on blank lines (two or more newlines).
    raw_blocks = re.split(r"\n{2,}", section.text.strip())
    blocks = [b.strip() for b in raw_blocks if b.strip()]

    if not blocks:
        return []

    chunks: list[Chunk] = []
    for block in blocks:
        if _is_table(block):
            chunks.extend(_chunk_table(block, name, order))
        elif _is_list(block):
            chunks.extend(_chunk_list(block, name, order))
        else:
            chunks.extend(_chunk_paragraph(block, name, order))

    chunks = _merge_undersize(chunks)
    chunks = _add_overlap(chunks)
    return chunks
