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
    # Normal paragraph, then hard-split paragraph, then another normal paragraph
    # This tests overlap at both edges of the hard-split: entering and exiting
    para1 = "Normal text. " * 300  # ~3600 chars
    para2 = "x" * 10000  # Hard-split at 6000 chars each
    para3 = "More text. " * 300  # ~3300 chars
    text = "\n\n".join([para1, para2, para3])
    chunks = chunk_text(text, max_chars=6000, overlap=200)

    # Find which chunk contains para3 (should be one of the last chunks)
    para3_chunk_idx = None
    for i, chunk in enumerate(chunks):
        if "More text." in chunk:
            para3_chunk_idx = i
            break

    assert para3_chunk_idx is not None
    assert para3_chunk_idx > 0

    # Verify overlap at exit boundary: last hard-split chunk should have its last 200 chars
    # repeated at the start of the chunk containing para3
    last_hard_split_chunk = chunks[para3_chunk_idx - 1]
    para3_chunk = chunks[para3_chunk_idx]
    overlap_text = last_hard_split_chunk[-200:]
    assert overlap_text in para3_chunk, "Overlap missing between hard-split and following normal paragraph"
