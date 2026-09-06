from unittest.mock import patch, MagicMock
from app.generation import generate_answer

SAMPLE_PASSAGE = {
    "id": 1, "source": "gujarat", "gazette_id": "Gujarat-Extra-62", "part": "Part IV-A",
    "section": None, "notification_date": "20th May, 2025",
    "operative_text": "...the Government of Gujarat hereby appoints the person specified...",
    "source_url": None, "score": 0.9,
}


def test_generate_answer_refuses_when_no_passages_found():
    result = generate_answer("What's the minimum wage in Delhi?", passages=[], history=[])
    assert result.refused is True
    assert "couldn't find" in result.answer.lower()
    assert result.citations == []
    assert "not legal advice" in result.disclaimer.lower()


def test_generate_answer_cites_a_real_passage_when_found():
    fake_response = MagicMock()
    fake_response.text = "Yes — Gujarat appointed the authority for the Code on Wages on 20 May 2025."

    with patch("app.generation._client") as mock_client:
        mock_client.models.generate_content.return_value = fake_response
        result = generate_answer(
            "Is the Code on Wages in force in Gujarat?", passages=[SAMPLE_PASSAGE], history=[]
        )

    assert result.refused is False
    assert len(result.citations) == 1
    assert result.citations[0].gazette_id == "Gujarat-Extra-62"
    assert "not legal advice" in result.disclaimer.lower()
