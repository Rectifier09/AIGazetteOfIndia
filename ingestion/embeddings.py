# ingestion/embeddings.py
import requests
from config import NVIDIA_API_KEY

NVIDIA_EMBEDDINGS_URL = "https://integrate.api.nvidia.com/v1/embeddings"

# nv-embedqa-1b-v2 is trained with Matryoshka Representation Learning, so
# requesting 768 dims directly returns a properly-formed embedding at that
# size (not a naive/degraded truncation of a larger vector) — and it matches
# the notifications.embedding column, which is vector(768) (migrations/001_init.sql).
EMBEDDING_MODEL = "nvidia/llama-3.2-nv-embedqa-1b-v2"
EMBEDDING_DIMENSIONS = 768


def embed_text(text: str, input_type: str = "passage") -> list[float]:
    """input_type must be "passage" when embedding a stored document (the only
    thing this ingestion package does) or "query" when embedding a user's
    question at retrieval time (a future caller, e.g. the Query API) — NV-Embed
    docs warn that mismatching the two causes real retrieval-quality drops."""
    if not NVIDIA_API_KEY:
        raise RuntimeError("NVIDIA_API_KEY is not set — cannot call the embedding API.")
    response = requests.post(
        NVIDIA_EMBEDDINGS_URL,
        headers={
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={
            "input": [text],
            "model": EMBEDDING_MODEL,
            "input_type": input_type,
            "dimensions": EMBEDDING_DIMENSIONS,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]
