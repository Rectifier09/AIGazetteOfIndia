import pytest
from unittest.mock import patch, MagicMock
from app.embeddings import embed_text, EMBEDDING_MODEL, NVIDIA_EMBEDDINGS_URL


def _fake_response(vector):
    fake = MagicMock()
    fake.json.return_value = {"data": [{"embedding": vector}]}
    fake.raise_for_status.return_value = None
    return fake


def test_embed_text_returns_vector_from_nvidia_response():
    with patch("app.embeddings.NVIDIA_API_KEY", "test-key"), \
         patch("app.embeddings.requests.post", return_value=_fake_response([0.1, 0.2, 0.3])) as mock_post:
        result = embed_text("Is the Code on Wages in force in Gujarat?")

    assert result == [0.1, 0.2, 0.3]
    call = mock_post.call_args
    assert call.args[0] == NVIDIA_EMBEDDINGS_URL
    assert call.kwargs["json"]["model"] == EMBEDDING_MODEL
    assert call.kwargs["json"]["dimensions"] == 768


def test_embed_text_defaults_to_query_input_type():
    with patch("app.embeddings.NVIDIA_API_KEY", "test-key"), \
         patch("app.embeddings.requests.post", return_value=_fake_response([0.0] * 768)) as mock_post:
        embed_text("Is the Code on Wages in force in Gujarat?")

    assert mock_post.call_args.kwargs["json"]["input_type"] == "query"


def test_embed_text_raises_a_clear_error_when_the_api_key_is_missing():
    with patch("app.embeddings.NVIDIA_API_KEY", ""):
        with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
            embed_text("anything")
