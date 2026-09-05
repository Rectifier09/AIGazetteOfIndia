# ingestion/embeddings.py
from google import genai
from config import GEMINI_API_KEY

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

EMBEDDING_MODEL = "gemini-embedding-001"


def embed_text(text: str) -> list[float]:
    response = _client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
    return list(response.embeddings[0].values)
