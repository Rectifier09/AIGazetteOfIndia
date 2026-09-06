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

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current.strip():
                chunks.append(current.strip())
                current = ""
            step = max_chars - overlap
            for start in range(0, len(paragraph), step):
                chunks.append(paragraph[start:start + max_chars])
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars:
            chunks.append(current.strip())
            carry = current[-overlap:] if current else ""
            restarted = f"{carry}\n\n{paragraph}" if carry.strip() else paragraph
            # Guard: if the carried-over overlap plus this paragraph would
            # itself exceed max_chars, drop the carry rather than violate the
            # max_chars contract on the next chunk (paragraph alone is
            # already known to be <= max_chars from the check above).
            current = restarted if len(restarted) <= max_chars else paragraph
        else:
            current = candidate

    if current.strip():
        chunks.append(current.strip())

    return chunks
