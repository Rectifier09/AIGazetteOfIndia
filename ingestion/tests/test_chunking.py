import pytest
from chunking import chunk_text


def test_short_text_produces_one_chunk():
    text = "A short single-paragraph notification."
    assert chunk_text(text) == [text]


def test_empty_text_produces_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_long_text_splits_on_paragraph_boundaries():
    paragraphs = ["Paragraph one. " * 100, "Paragraph two. " * 100, "Paragraph three. " * 100]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_chars=2000, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 2000 for c in chunks)
    assert "Paragraph one." in chunks[0]
    assert "Paragraph three." in chunks[-1]


def test_oversized_single_paragraph_is_hard_split():
    text = "x" * 20000  # one giant "paragraph", no blank lines at all
    chunks = chunk_text(text, max_chars=6000, overlap=200)
    assert len(chunks) > 1
    assert all(len(c) <= 6000 for c in chunks)
    assert all(c.strip("x") == "" for c in chunks)  # every chunk is pure "x" (overlap repeats some)


def test_overlap_is_present_between_consecutive_packed_chunks():
    paragraphs = ["A" * 3000, "B" * 3000, "C" * 3000]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_chars=6000, overlap=200)
    assert len(chunks) >= 2
    assert chunks[0][-200:] in chunks[1]


def test_overlap_at_hard_split_boundaries():
    # Distinguishable content on each side of the hard split lets this test
    # prove exactly which characters crossed which boundary, instead of a
    # same-character-filler window that could match anywhere.
    para1 = "AAA1. " * 500
    hard = "B" * 10000
    para3 = "CCC3. " * 500
    text = f"{para1}\n\n{hard}\n\n{para3}"
    chunks = chunk_text(text, max_chars=6000, overlap=200)

    # Entry boundary: para1's own chunk and the hard split's first slice
    # share exactly `overlap` characters.
    para1_idx = chunks.index(para1.strip())
    assert chunks[para1_idx][-200:] == chunks[para1_idx + 1][:200]

    # Exit boundary: the hard split's last slice and whatever chunk para3
    # ends up in share exactly `overlap` characters.
    para3_idx = next(i for i, c in enumerate(chunks) if para3.strip() in c)
    assert chunks[para3_idx - 1][-200:] == chunks[para3_idx][:200]


def test_consecutive_oversized_paragraphs_no_duplicates():
    para1 = "P" * 10000
    para2 = "Q" * 10000
    text = f"{para1}\n\n{para2}"
    chunks = chunk_text(text, max_chars=6000, overlap=200)

    assert len(chunks) == len(set(chunks))
    assert all(len(c) <= 6000 for c in chunks)
    # The bare carry-seed from the first hard split must never become its
    # own standalone chunk when the second hard split immediately follows.
    assert "P" * 200 not in chunks


def test_hard_split_followed_by_paragraph_too_big_for_seed_produces_no_duplicate_chunk():
    text = "x" * 10000 + "\n\n" + "y" * 5900
    chunks = chunk_text(text, max_chars=6000, overlap=200)
    assert len(chunks) == len(set(chunks))
    assert all(len(c) <= 6000 for c in chunks)


def test_carry_recovers_real_content_past_trailing_whitespace():
    text = "IMPORTANT-CONTENT" + " " * 300 + "\n\n" + "q" * 8000
    chunks = chunk_text(text, max_chars=6000, overlap=200)
    assert any("IMPORTANT-CONTENT" in c for c in chunks)


def test_overlap_must_be_smaller_than_max_chars():
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("some text", max_chars=100, overlap=100)
