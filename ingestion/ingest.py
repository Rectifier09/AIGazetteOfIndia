# ingestion/ingest.py
import hashlib
import psycopg
from chunking import chunk_text
from extractor import parse_central, parse_gujarat
from embeddings import embed_text
from storage import insert_notification, insert_chunks

PARSERS = {"central": parse_central, "gujarat": parse_gujarat}


class OutOfScopeError(Exception):
    """The document parsed fine but is not a Labour Code notification.

    Ministry 28's monthly listings mix Labour Code notifications in with
    unrelated ones (mines, uranium, fuel gas, ...) — empirically only about one
    in six is in scope. A non-None act_reference means the extractor matched a
    "Code on <name>, <year> (<n> of <year>)" citation, which is a reliable
    in-scope signal. Raising instead of inserting keeps off-topic documents out
    of the database and, because the check runs before any embedding work,
    avoids spending a paid embedding call on them.
    """


def ingest_notification(
    conn: psycopg.Connection,
    source: str,
    raw_text: str,
    known_gazette_id: str | None = None,
    source_url: str | None = None,
) -> int:
    if source not in PARSERS:
        raise ValueError(f"Unknown source: {source!r}. Must be 'central' or 'gujarat'.")

    file_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    record = PARSERS[source](raw_text)

    # The discovery step reads gazette_id straight out of the search results
    # table, which is far more trustworthy than the value regexed out of the
    # PDF text: real gazette PDFs carry a security watermark that makes
    # pdfplumber interleave characters, mangling the ID (or losing it entirely).
    if known_gazette_id is not None:
        record.gazette_id = known_gazette_id

    if record.act_reference is None:
        raise OutOfScopeError(
            f"No Labour Code act reference found in {record.gazette_id or 'document'} — "
            "not a Labour Code notification."
        )

    notification_id, is_new = insert_notification(
        conn, record, file_hash=file_hash, source_url=source_url
    )
    if is_new:
        # Only a genuinely new row pays for chunking/embedding — re-ingesting
        # an already-present notification now costs one cheap lookup-and-skip
        # instead of a wasted embedding API call per chunk.
        chunks = chunk_text(record.operative_text)
        embedded_chunks = [(chunk, embed_text(chunk)) for chunk in chunks]
        insert_chunks(conn, notification_id, embedded_chunks)
    return notification_id
