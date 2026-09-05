# ingestion/tests/test_embeddings.py
import pytest
from unittest.mock import patch, MagicMock
from embeddings import embed_text, EMBEDDING_MODEL, NVIDIA_EMBEDDINGS_URL


def _fake_response(vector):
    fake = MagicMock()
    fake.json.return_value = {
        "object": "list",
        "data": [{"object": "embedding", "index": 0, "embedding": vector}],
        "model": EMBEDDING_MODEL,
        "usage": {"prompt_tokens": 5, "total_tokens": 5},
    }
    fake.raise_for_status.return_value = None
    return fake


def test_embed_text_returns_vector_from_nvidia_response():
    with patch("embeddings.NVIDIA_API_KEY", "test-key"), \
         patch("embeddings.requests.post", return_value=_fake_response([0.1, 0.2, 0.3])) as mock_post:
        result = embed_text("Code on Wages, 2019")

    assert result == [0.1, 0.2, 0.3]
    mock_post.assert_called_once()
    call = mock_post.call_args
    assert call.args[0] == NVIDIA_EMBEDDINGS_URL
    assert call.kwargs["json"]["model"] == EMBEDDING_MODEL
    assert call.kwargs["json"]["input"] == ["Code on Wages, 2019"]


def test_embed_text_requests_768_dimensions_to_match_the_vector_column():
    with patch("embeddings.NVIDIA_API_KEY", "test-key"), \
         patch("embeddings.requests.post", return_value=_fake_response([0.0] * 768)) as mock_post:
        embed_text("Code on Wages, 2019")

    call = mock_post.call_args
    assert call.kwargs["json"]["dimensions"] == 768


def test_embed_text_defaults_to_passage_input_type():
    with patch("embeddings.NVIDIA_API_KEY", "test-key"), \
         patch("embeddings.requests.post", return_value=_fake_response([0.0] * 768)) as mock_post:
        embed_text("Code on Wages, 2019")

    call = mock_post.call_args
    assert call.kwargs["json"]["input_type"] == "passage"


def test_embed_text_accepts_query_input_type_for_future_query_time_use():
    with patch("embeddings.NVIDIA_API_KEY", "test-key"), \
         patch("embeddings.requests.post", return_value=_fake_response([0.0] * 768)) as mock_post:
        embed_text("Is the Code on Wages in force in Gujarat?", input_type="query")

    call = mock_post.call_args
    assert call.kwargs["json"]["input_type"] == "query"


def test_embed_text_sends_bearer_auth_header():
    with patch("embeddings.NVIDIA_API_KEY", "test-key-123"), \
         patch("embeddings.requests.post", return_value=_fake_response([0.0] * 768)) as mock_post:
        embed_text("Code on Wages, 2019")

    call = mock_post.call_args
    assert call.kwargs["headers"]["Authorization"] == "Bearer test-key-123"


def test_embed_text_raises_a_clear_error_when_the_api_key_is_missing():
    with patch("embeddings.NVIDIA_API_KEY", ""):
        with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
            embed_text("Code on Wages, 2019")


def test_embed_text_raises_on_http_error():
    fake = MagicMock()
    fake.raise_for_status.side_effect = Exception("401 Unauthorized")
    with patch("embeddings.NVIDIA_API_KEY", "test-key"), \
         patch("embeddings.requests.post", return_value=fake):
        with pytest.raises(Exception, match="401 Unauthorized"):
            embed_text("Code on Wages, 2019")
