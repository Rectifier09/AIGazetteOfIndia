# ingestion/tests/test_embeddings.py
import pytest
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


def test_embed_text_requests_768_dimensions_to_match_the_vector_column():
    fake_response = MagicMock()
    fake_response.embeddings = [MagicMock(values=[0.0] * 768)]

    with patch("embeddings._client") as mock_client:
        mock_client.models.embed_content.return_value = fake_response
        embed_text("Code on Wages, 2019")

    call_kwargs = mock_client.models.embed_content.call_args.kwargs
    assert "config" in call_kwargs
    assert call_kwargs["config"].output_dimensionality == 768


def test_embed_text_raises_a_clear_error_when_the_api_key_is_missing():
    with patch("embeddings._client", None):
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            embed_text("Code on Wages, 2019")
