def chunk_text(text: str, max_chars: int = 6000, overlap: int = 200) -> list[str]:
    """Split text into chunks under max_chars, preferring paragraph boundaries.

    Splits on blank-line-separated paragraphs first, then greedily packs
    consecutive paragraphs into a chunk until adding the next one would
    exceed max_chars. A single paragraph longer than max_chars (possible
    given the bilingual/watermark-garbled text already observed in this
    domain) is hard-split at the character limit as a fallback, rather than
    crashing or silently dropping content. overlap characters are carried
    across every chunk boundary — including both edges of a hard split — so
    content split across a boundary isn't lost to whichever chunk actually
    gets matched by a search.
    """
    text = text.strip()
    if not text:
        return []
    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars")

    paragraphs = [p for p in text.split("\n\n") if p.strip()] or [text]

    chunks: list[str] = []
    current = ""
    # True only while `current` holds nothing but a carried-over overlap
    # tail from a hard split, with no real paragraph content merged in yet.
    # Flushing a bare seed as its own chunk would duplicate content already
    # present in the chunk it was carried from.
    current_is_seed = False

    def flush_current():
        nonlocal current, current_is_seed
        if current.strip() and not current_is_seed:
            chunks.append(current.strip())
        current = ""
        current_is_seed = False

    for index, paragraph in enumerate(paragraphs):
        is_last_paragraph = index == len(paragraphs) - 1

        if len(paragraph) > max_chars:
            # Strip before slicing: an unstripped current[-overlap:] can grab
            # pure trailing whitespace instead of real content when current
            # is short, silently losing that content once the empty-after-
            # strip carry gets discarded below.
            carry = current.strip()[-overlap:] if current.strip() else ""
            flush_current()

            prefix = f"{carry}\n\n" if carry.strip() else ""
            first_slice_len = max_chars - len(prefix)
            chunks.append(f"{prefix}{paragraph[:first_slice_len]}")

            step = max_chars - overlap
            pos = first_slice_len - overlap
            while pos < len(paragraph):
                if len(paragraph) - pos <= overlap:
                    # Nothing left beyond the overlap window — skip a slice
                    # that would be almost or entirely a repeat.
                    break
                chunks.append(paragraph[pos:pos + max_chars])
                pos += step

            if not is_last_paragraph:
                current = chunks[-1][-overlap:]
                current_is_seed = True
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars:
            carry = current.strip()[-overlap:] if current.strip() else ""
            flush_current()
            restarted = f"{carry}\n\n{paragraph}" if carry.strip() else paragraph
            current = restarted if len(restarted) <= max_chars else paragraph
            current_is_seed = False
        else:
            current = candidate
            current_is_seed = False

    flush_current()
    return chunks
