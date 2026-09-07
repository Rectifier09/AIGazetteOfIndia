# backend/app/main.py
# Auto-deploy verification: Railway GitHub App now has repo access (2026-09-07).
import logging
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.genai import errors as genai_errors
from app.config import get_connection
from app.retrieval import hybrid_search
from app.generation import generate_answer
from app.models import AskRequest, AskResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="e-Gazette Conversational Search — Query API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://aigazetteofindia.vercel.app",
        "https://frontend-nine-pi-0x0iky59ud.vercel.app",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    # Deliberately dependency-free — must answer even if Postgres or the AI
    # APIs are down. This is a liveness check, not a readiness check: it
    # confirms the process is running, not that /ask can currently succeed.
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    try:
        conn = get_connection()
    except Exception as exc:
        logger.exception("Database connection failed answering a question")
        raise HTTPException(
            status_code=503, detail="The database is temporarily unavailable — please try again shortly."
        ) from exc

    try:
        passages = hybrid_search(conn, request.question)
        history = [{"question": h.question, "answer": h.answer} for h in request.history]
        return generate_answer(request.question, passages, history)
    except (requests.HTTPError, genai_errors.ClientError, genai_errors.ServerError) as exc:
        logger.exception("Upstream AI service failure answering a question")
        raise HTTPException(
            status_code=503, detail="The service is temporarily unavailable — please try again shortly."
        ) from exc
    finally:
        conn.close()
