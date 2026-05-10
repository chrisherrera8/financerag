"""Pytest fixtures for building Chunk objects in tests."""

import pytest

from pipeline.chunker import Chunk


@pytest.fixture
def make_paragraph_chunk():
    """Return a factory for paragraph-level Chunk objects."""
    def _make(text: str, section_name: str = "Risk Factors", section_order: int = 1) -> Chunk:
        return Chunk(
            text=text,
            chunk_level="paragraph",
            token_count=len(text.split()),
            section_name=section_name,
            section_order=section_order,
        )
    return _make
