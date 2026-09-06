def chunk_text(text: str, max_chars: int = 6000, overlap: int = 200) -> list[str]:
    """Split text into chunks under max_chars, preferring paragraph boundaries.

    Splits on blank-line-separated paragraphs first, then greedily packs
    consecutive paragraphs into a chunk until adding the next one would
    exceed max_chars. A single paragraph longer than max_chars is hard-split
    at the character limit (real gazette PDFs occasionally produce this via
    watermark-garbled text with no paragraph breaks at all). overlap
    characters from the end of each chunk are carried into the start of the
    next, so content split across a chunk boundary isn't lost to whichever
    chunk actually gets matched by a search. max_chars=6000 is deliberately
    conservative relative to the embedding model's 8,192-token limit — see
    the design spec for the token/char ratio this was measured against.
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p for p in text.split("\n\n") if p.strip()] or [text]

    chunks: list[str] = []
    current = ""

    for index, paragraph in enumerate(paragraphs):
        is_last_paragraph = index == len(paragraphs) - 1

        if len(paragraph) > max_chars:
            # Entry side: carry the tail of whatever chunk precedes this hard
            # split into its first slice, sized so the carry-prefixed slice
            # still respects max_chars. Only flush `current` as its own chunk
            # if it holds more than a bare carry-seed left over from an
            # earlier hard split (len(current) > overlap) — otherwise a run
            # of consecutive oversized paragraphs would emit that seed twice:
            # once as its own tiny chunk, once again as the next slice's prefix.
            carry = ""
            if current.strip():
                carry = current[-overlap:]
                if len(current.strip()) > overlap:
                    chunks.append(current.strip())
                current = ""

            prefix = f"{carry}\n\n" if carry.strip() else ""
            first_slice_len = max_chars - len(prefix)
            chunks.append(f"{prefix}{paragraph[:first_slice_len]}")

            step = max_chars - overlap
            pos = first_slice_len - overlap
            while pos < len(paragraph):
                chunks.append(paragraph[pos:pos + max_chars])
                pos += step

            # Exit side: carry the tail of the last hard-split slice into
            # whatever chunk begins next, so the boundary leaving the hard
            # split also overlaps. Skip this when the hard split is the last
            # paragraph — there's nothing left to carry into, and doing it
            # anyway would leave a bare carry-seed that the final flush below
            # would emit as a spurious extra chunk.
            if not is_last_paragraph:
                current = chunks[-1][-overlap:]
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars:
            chunks.append(current.strip())
            carry = current[-overlap:] if current else ""
            restarted = f"{carry}\n\n{paragraph}" if carry.strip() else paragraph
            current = restarted if len(restarted) <= max_chars else paragraph
        else:
            current = candidate

    if current.strip():
        chunks.append(current.strip())

    return chunks
