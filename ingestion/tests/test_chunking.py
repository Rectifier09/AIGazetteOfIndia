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
