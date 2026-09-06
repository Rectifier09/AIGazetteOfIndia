from unittest.mock import patch
from app.retrieval import hybrid_search


def test_hybrid_search_finds_notification_by_keyword(insert_test_notification, db_conn):
    insert_test_notification(
        gazette_id="Gujarat-Extra-62",
        operative_text="the Government of Gujarat hereby appoints the person specified as the "
                        "Authority for the purposes of the Code on Wages, 2019",
        embedding=[0.1] * 768,
        source="gujarat",
    )

    with patch("app.retrieval.embed_text", return_value=[0.1] * 768):
        results = hybrid_search(db_conn, "Code on Wages Gujarat appointing authority")

    assert len(results) >= 1
    assert results[0]["gazette_id"] == "Gujarat-Extra-62"


def test_hybrid_search_returns_empty_list_when_nothing_ingested(db_conn):
    with patch("app.retrieval.embed_text", return_value=[0.1] * 768):
        results = hybrid_search(db_conn, "anything at all")
    assert results == []


def test_hybrid_search_collapses_multiple_matching_chunks_to_the_best_one(insert_test_notification, db_conn):
    notification_id = insert_test_notification(
        gazette_id="Multi-Chunk-1",
        operative_text="a chunk with only a partial keyword match: wages",
        embedding=[0.1] * 768,
        source="central",
    )
    db_conn.execute(
        """
        INSERT INTO notification_chunks (notification_id, chunk_index, chunk_text, embedding)
        VALUES (%s, %s, %s, %s)
        """,
        (notification_id, 1, "a chunk with the full keyword match: Code on Wages appointing authority", [0.1] * 768),
    )
    db_conn.commit()

    with patch("app.retrieval.embed_text", return_value=[0.1] * 768):
        results = hybrid_search(db_conn, "Code on Wages appointing authority")

    assert len(results) == 1
    assert "full keyword match" in results[0]["operative_text"]
