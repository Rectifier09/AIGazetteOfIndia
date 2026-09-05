# ingestion/embeddings.py
from google import genai
from config import GEMINI_API_KEY

# Use a dummy key for testing if real key is not available
api_key = GEMINI_API_KEY or "dummy-key-for-testing"
_client = genai.Client(api_key=api_key)

EMBEDDING_MODEL = "gemini-embedding-001"


def embed_text(text: str) -> list[float]:
    response = _client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
    return list(response.embeddings[0].values)
