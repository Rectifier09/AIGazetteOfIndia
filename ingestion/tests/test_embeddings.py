# ingestion/tests/test_embeddings.py
from unittest.mock import patch, MagicMock
from embeddings import embed_text


def test_embed_text_returns_vector_from_gemini_response():
    fake_response = MagicMock()
    fake_response.embeddings = [MagicMock(values=[0.1, 0.2, 0.3])]

    with patch("embeddings._client") as mock_client:
        mock_client.models.embed_content.return_value = fake_response
        result = embed_text("Code on Wages, 2019")

    assert result == [0.1, 0.2, 0.3]
    mock_client.models.embed_content.assert_called_once()
    call_kwargs = mock_client.models.embed_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-embedding-001"
