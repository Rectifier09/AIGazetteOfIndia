from fastapi import FastAPI
from app.config import get_connection
from app.retrieval import hybrid_search
from app.generation import generate_answer
from app.models import AskRequest, AskResponse

app = FastAPI(title="e-Gazette Conversational Search — Query API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    conn = get_connection()
    try:
        passages = hybrid_search(conn, request.question)
        return generate_answer(request.question, passages, request.history)
    finally:
        conn.close()
