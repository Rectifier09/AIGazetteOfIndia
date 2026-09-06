from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_returns_cited_answer_for_existing_notification(insert_test_notification, db_conn):
    insert_test_notification(
        gazette_id="Gujarat-Extra-62",
        operative_text="the Government of Gujarat hereby appoints the person specified as the "
                        "Authority for the purposes of the Code on Wages, 2019",
        embedding=[0.1] * 768,
        source="gujarat",
    )

    with patch("app.retrieval.embed_text", return_value=[0.1] * 768), \
         patch("app.generation._client") as mock_genai:
        mock_genai.models.generate_content.return_value.text = "Yes, it is in force."
        ask_response = client.post(
            "/ask", json={"question": "Is the Code on Wages in force in Gujarat?", "history": []}
        )

    assert ask_response.status_code == 200
    body = ask_response.json()
    assert body["refused"] is False
    assert body["citations"][0]["gazette_id"] == "Gujarat-Extra-62"
    assert "not legal advice" in body["disclaimer"].lower()


def test_ask_refuses_when_nothing_matches(db_conn):
    with patch("app.retrieval.embed_text", return_value=[0.1] * 768):
        response = client.post("/ask", json={"question": "What's the weather today?", "history": []})
    assert response.status_code == 200
    assert response.json()["refused"] is True
