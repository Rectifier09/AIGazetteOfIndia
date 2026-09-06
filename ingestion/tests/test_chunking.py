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

    # Find chunks containing para1 and para3
    para1_chunk_idx = None
    para3_chunk_idx = None
    for i, chunk in enumerate(chunks):
        if "Normal text." in chunk:
            para1_chunk_idx = i
        if "More text." in chunk:
            para3_chunk_idx = i

    assert para1_chunk_idx is not None
    assert para3_chunk_idx is not None
    assert para3_chunk_idx > para1_chunk_idx

    # Verify entry-side overlap: para1 chunk should have overlap at the start of the first hard-split chunk
    para1_chunk = chunks[para1_chunk_idx]
    first_hard_split_chunk = chunks[para1_chunk_idx + 1]
    entry_overlap = para1_chunk[-200:]
    assert entry_overlap in first_hard_split_chunk, "Overlap missing at entry to hard-split"

    # Verify exit-side overlap: last hard-split chunk should have its last 200 chars in para3 chunk
    last_hard_split_chunk = chunks[para3_chunk_idx - 1]
    para3_chunk = chunks[para3_chunk_idx]
    exit_overlap = last_hard_split_chunk[-200:]
    assert exit_overlap in para3_chunk, "Overlap missing at exit from hard-split"


def test_consecutive_oversized_paragraphs_no_duplicates():
    # Two consecutive oversized paragraphs separated by blank lines
    # Should produce hard-split chunks with overlap but no duplicate carry-seed chunks
    para1 = "a" * 10000
    para2 = "b" * 10000
    text = "\n\n".join([para1, para2])
    chunks = chunk_text(text, max_chars=6000, overlap=200)

    # Should have multiple chunks from both hard-splits
    assert len(chunks) >= 4

    # All chunks should be <= max_chars
    assert all(len(c) <= 6000 for c in chunks)

    # Check that no chunk appears twice (no duplicates of carry-seed)
    assert len(chunks) == len(set(chunks)), "Duplicate chunks found"

    # Verify overlap between the boundary of the two hard-splits
    # Find the transition point between para1's hard-split and para2's hard-split
    transition_idx = None
    for i in range(len(chunks) - 1):
        # para1 chunks contain only 'a', para2 chunks contain only 'b' (after transition)
        # Look for the chunk before the first 'b'-only chunk
        if chunks[i].strip("a") == "" and chunks[i + 1].strip("b") == "":
            transition_idx = i
            break

    if transition_idx is not None:
        # The transition chunks should have overlap
        boundary_overlap = chunks[transition_idx][-200:]
        assert boundary_overlap in chunks[transition_idx + 1], "Overlap missing between consecutive hard-splits"
