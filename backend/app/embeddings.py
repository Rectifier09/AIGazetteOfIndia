import requests
from app.config import NVIDIA_API_KEY

NVIDIA_EMBEDDINGS_URL = "https://integrate.api.nvidia.com/v1/embeddings"
EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"
EMBEDDING_DIMENSIONS = 768


def embed_text(text: str, input_type: str = "query") -> list[float]:
    """input_type defaults to "query" here — this service only ever embeds the
    user's question, never a stored document (that's the ingestion pipeline's
    job, which defaults to "passage"). Mismatching the two degrades retrieval
    quality per NV-Embed's own documentation."""
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
