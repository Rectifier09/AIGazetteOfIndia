# ingestion/ingest.py
import hashlib
import psycopg
from extractor import parse_central, parse_gujarat
from embeddings import embed_text
from storage import insert_notification

PARSERS = {"central": parse_central, "gujarat": parse_gujarat}


def ingest_notification(conn: psycopg.Connection, source: str, raw_text: str) -> int:
    if source not in PARSERS:
        raise ValueError(f"Unknown source: {source!r}. Must be 'central' or 'gujarat'.")

    file_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    record = PARSERS[source](raw_text)
    embedding = embed_text(record.operative_text)
    return insert_notification(conn, record, embedding=embedding, file_hash=file_hash)
