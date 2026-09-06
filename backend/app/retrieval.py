import psycopg
from app.embeddings import embed_text

RRF_K = 60  # standard reciprocal-rank-fusion constant


def _keyword_search(conn: psycopg.Connection, question: str, top_k: int) -> list[tuple[int, int]]:
    rows = conn.execute(
        """
        SELECT id, ts_rank(to_tsvector('english', chunk_text), plainto_tsquery('english', %s)) AS rank
        FROM notification_chunks
        WHERE to_tsvector('english', chunk_text) @@ plainto_tsquery('english', %s)
        ORDER BY rank DESC
        LIMIT %s
        """,
        (question, question, top_k),
    ).fetchall()
    return [(row[0], position) for position, row in enumerate(rows)]


def _vector_search(conn: psycopg.Connection, question: str, top_k: int) -> list[tuple[int, int]]:
    query_embedding = embed_text(question, input_type="query")
    rows = conn.execute(
        """
        SELECT id FROM notification_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (query_embedding, top_k),
    ).fetchall()
    return [(row[0], position) for position, row in enumerate(rows)]


def hybrid_search(conn: psycopg.Connection, question: str, top_k: int = 5) -> list[dict]:
    keyword_hits = _keyword_search(conn, question, top_k)
    vector_hits = _vector_search(conn, question, top_k)

    chunk_scores: dict[int, float] = {}
    for chunk_id, rank in keyword_hits + vector_hits:
        chunk_scores[chunk_id] = chunk_scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)

    if not chunk_scores:
        return []

    rows = conn.execute(
        """
        SELECT c.id, c.notification_id, c.chunk_text, n.source, n.gazette_id, n.part,
               n.section, n.notification_date, n.source_url
        FROM notification_chunks c
        JOIN notifications n ON n.id = c.notification_id
        WHERE c.id = ANY(%s)
        """,
        (list(chunk_scores.keys()),),
    ).fetchall()

    # One citation per notification: if several of its chunks scored well,
    # keep only the best-scoring one (spec §6 — preserves the existing
    # one-passage-per-source Citation model rather than expanding it).
    best_per_notification: dict[int, dict] = {}
    for row in rows:
        chunk_id, notification_id = row[0], row[1]
        score = chunk_scores[chunk_id]
        candidate = {
            "id": notification_id, "source": row[3], "gazette_id": row[4], "part": row[5],
            "section": row[6], "notification_date": row[7], "operative_text": row[2],
            "source_url": row[8], "score": score,
        }
        existing = best_per_notification.get(notification_id)
        if existing is None or score > existing["score"]:
            best_per_notification[notification_id] = candidate

    return sorted(best_per_notification.values(), key=lambda r: r["score"], reverse=True)[:top_k]
