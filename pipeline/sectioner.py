"""Split a parsed SEC filing HTML into named sections based on Item/Part headers."""

import re
import warnings
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

_HEADER_RE = re.compile(r"^(PART\s+[IVX]+|Item\s+\d+[A-Z]?\.)", re.IGNORECASE)


@dataclass
class Section:
    """A named SEC filing section extracted from a 10-K or similar document.

    Attributes:
        section_name: Normalized header text (e.g. ``"Item 1. Business"``).
        section_order: 1-based position in document order.
        text: Plain text content belonging to this section.
    """

    section_name: str
    section_order: int
    text: str = field(default="")


def _normalize(text: str) -> str:
    """Collapse internal whitespace and strip edges."""
    return re.sub(r"\s+", " ", text).strip()


def _is_bold(tag: Tag) -> bool:
    """Return True if *tag* applies bold styling."""
    name = tag.name.lower() if tag.name else ""
    if name in ("b", "strong"):
        return True
    if name == "font":
        style = tag.get("style", "")
        return "font-weight:bold" in style.replace(" ", "").lower()
    if name == "span":
        style = tag.get("style", "")
        return "font-weight:700" in style.replace(" ", "").lower() or \
               "font-weight:bold" in style.replace(" ", "").lower()
    return False


def _inside_href_anchor(tag: Tag) -> bool:
    """Return True if *tag* is a descendant of an <a href="..."> element."""
    for parent in tag.parents:
        if not isinstance(parent, Tag):
            continue
        if parent.name and parent.name.lower() == "a" and parent.get("href"):
            return True
    return False


def _bold_header_text(tag: Tag) -> str | None:
    """Return the normalized header text if *tag* is a bold SEC header, else None."""
    if not _is_bold(tag):
        return None
    text = _normalize(tag.get_text())
    if _HEADER_RE.match(text):
        return text
    return None


def _adjacent_cell_title(tag: Tag) -> str | None:
    """Check if *tag* is inside a <td> whose next sibling <td> provides a title.

    Handles filings where the bold label sits inside nested elements
    (e.g. ``<td><div><font>ITEM 1.</font></div></td>``).  Walks up the
    ancestor chain to find the enclosing ``<td>``, then looks at the
    next sibling ``<td>`` for the title text.

    Returns the assembled ``"Label Title"`` string, or ``None``.
    """
    label = _normalize(tag.get_text())
    if not _HEADER_RE.match(label):
        return None
    # Walk up to the nearest <td> ancestor
    ancestor = tag.parent
    while ancestor is not None and isinstance(ancestor, Tag):
        if ancestor.name.lower() == "td":
            break
        ancestor = ancestor.parent
    else:
        return None
    if ancestor is None or not isinstance(ancestor, Tag):
        return None
    # Walk to next non-empty sibling <td>
    sibling = ancestor.next_sibling
    while sibling is not None:
        if isinstance(sibling, Tag) and sibling.name.lower() == "td":
            title = _normalize(sibling.get_text())
            if title:
                sep = " " if label.endswith(".") else ". "
                return f"{label}{sep}{title}"
            break
        sibling = sibling.next_sibling
    return None


def _collect_boundaries(soup: BeautifulSoup) -> list[tuple[Tag, str]]:
    """Return ``(tag, header_text)`` pairs for every valid section boundary."""
    seen: set[int] = set()
    boundaries: list[tuple[Tag, str]] = []

    # Tier 1: bold-styled elements
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        if _inside_href_anchor(tag):
            continue
        header = _bold_header_text(tag)
        if header is None:
            continue
        # Check for legacy adjacent-cell assembly
        assembled = _adjacent_cell_title(tag)
        name = assembled if assembled else header
        name = _normalize(name)
        tid = id(tag)
        if tid not in seen:
            seen.add(tid)
            boundaries.append((tag, name))

    if boundaries:
        return boundaries

    # Tier 2 fallback: regex on all text-bearing elements regardless of bold
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        if _inside_href_anchor(tag):
            continue
        text = _normalize(tag.get_text())
        if _HEADER_RE.match(text) and id(tag) not in seen:
            seen.add(id(tag))
            boundaries.append((tag, text))

    return boundaries


def split_sections(html: str) -> list[Section]:
    """Split an SEC filing HTML string into named :class:`Section` objects.

    Detection is tiered: bold Item/Part elements are preferred; plain-text
    regex is used as a fallback for unstyled filings.  TOC links (``<a href>``)
    are skipped.  Content before the first detected header is assigned the
    section name ``"Other"``.

    Args:
        html: Raw HTML string of the SEC filing.

    Returns:
        List of :class:`Section` objects in document order, each with
        ``section_name``, ``section_order``, and ``text`` populated.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(html, "lxml")

    boundaries = _collect_boundaries(soup)

    # Build a flat list of all text nodes with their source tag positions
    # to assign text ranges between boundaries.
    all_tags = list(soup.find_all(True))
    boundary_tag_ids = {id(tag): name for tag, name in boundaries}

    # Walk document in source order; collect (position, type, payload)
    # We'll use a simpler approach: get the document's text split by boundary tags.
    # Strategy: serialise the tree, find boundary tag positions, slice text.

    # Build ordered list of (boundary_tag, name) in document order
    ordered: list[tuple[Tag, str]] = []
    for tag in soup.find_all(True):
        if id(tag) in boundary_tag_ids:
            ordered.append((tag, boundary_tag_ids[id(tag)]))

    if not ordered:
        # No sections found — return the whole document as "Other"
        return [Section(section_name="Other", section_order=1, text=_normalize(soup.get_text()))]

    sections: list[Section] = []
    order = 1

    def _text_before(boundary_tag: Tag, prev_tag: Tag | None) -> str:
        """Collect text from elements between prev_tag and boundary_tag."""
        collecting = prev_tag is None
        parts: list[str] = []
        for t in soup.find_all(True):
            if prev_tag is not None and t is prev_tag:
                collecting = True
                continue
            if t is boundary_tag:
                break
            if collecting:
                # Only leaf-level text to avoid double-counting
                if not t.find(True):
                    chunk = _normalize(t.get_text())
                    if chunk:
                        parts.append(chunk)
        return " ".join(parts)

    def _text_after(boundary_tag: Tag, next_tag: Tag | None) -> str:
        """Collect text from elements after boundary_tag up to next_tag."""
        collecting = False
        parts: list[str] = []
        for t in soup.find_all(True):
            if t is boundary_tag:
                collecting = True
                continue
            if next_tag is not None and t is next_tag:
                break
            if collecting:
                if not t.find(True):
                    chunk = _normalize(t.get_text())
                    if chunk:
                        parts.append(chunk)
        return " ".join(parts)

    # Preamble ("Other") before the first boundary
    preamble = _text_before(ordered[0][0], None)
    if preamble.strip():
        sections.append(Section(section_name="Other", section_order=order, text=preamble))
        order += 1

    for i, (tag, name) in enumerate(ordered):
        next_tag = ordered[i + 1][0] if i + 1 < len(ordered) else None
        content = _text_after(tag, next_tag)
        sections.append(Section(section_name=name, section_order=order, text=content))
        order += 1

    return sections
