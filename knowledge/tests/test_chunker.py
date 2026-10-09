"""Unit tests for indexing.indexer.chunk_body — no Postgres needed."""

from kairos_knowledge.indexing.indexer import chunk_body


def test_splits_by_heading():
    body = "## Goal\n\nDo the thing.\n\n## Status\n\nOn track.\n"
    chunks = chunk_body("Title", body)
    assert [h for h, _ in chunks] == ["Goal", "Status"]
    assert chunks[0][1] == "Do the thing."
    assert chunks[1][1] == "On track."


def test_no_headings_is_one_chunk():
    body = "Just a paragraph, no headings at all."
    chunks = chunk_body("Title", body)
    assert len(chunks) == 1
    assert chunks[0] == (None, body)


def test_preamble_before_first_heading_kept():
    body = "Intro text.\n\n## Details\n\nMore.\n"
    chunks = chunk_body("Title", body)
    assert chunks[0] == (None, "Intro text.")
    assert chunks[1][0] == "Details"


def test_long_section_split_on_paragraphs():
    para = "word " * 200  # ~250 tokens per paragraph at 4 chars/token
    body = f"## Big\n\n{para}\n\n{para}\n\n{para}\n"
    chunks = chunk_body("Title", body)
    headings = [h for h, _ in chunks]
    assert headings.count("Big") > 1, "a >400-token section must split into multiple chunks"
    for _, text in chunks:
        assert text  # no empty chunks


def test_empty_body_yields_one_chunk():
    chunks = chunk_body("Title", "")
    assert chunks == [(None, "")]
