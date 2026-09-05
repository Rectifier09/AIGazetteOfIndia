# ingestion/embeddings.py
from google import genai
from google.genai import types
from config import GEMINI_API_KEY

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

EMBEDDING_MODEL = "gemini-embedding-001"

# The notifications.embedding column is vector(768) (migrations/001_init.sql).
# gemini-embedding-001 defaults to 3072 dimensions, so the request must ask for
# 768 explicitly or every insert fails on a dimension mismatch.
EMBEDDING_DIMENSIONS = 768


def embed_text(text: str) -> list[float]:
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY is not set — cannot call the embedding API.")
    response = _client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
    )
    return list(response.embeddings[0].values)
