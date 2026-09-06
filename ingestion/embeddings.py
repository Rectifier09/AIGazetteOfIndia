# ingestion/embeddings.py
import requests
from config import NVIDIA_API_KEY

NVIDIA_EMBEDDINGS_URL = "https://integrate.api.nvidia.com/v1/embeddings"

# llama-3.2-nv-embedqa-1b-v2 reached end-of-life 2026-05-18 and returns 410 Gone.
# llama-nemotron-embed-vl-1b-v2 is its successor and is Matryoshka-trained too,
# so requesting 768 dims directly returns a properly-formed embedding at that
# size (not a naive/degraded truncation of a larger vector) — verified live
# against the real API. Matches the notification_chunks.embedding column,
# which is vector(768) (migrations/001_init.sql).
EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"
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
