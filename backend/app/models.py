# backend/app/models.py
from pydantic import BaseModel, Field


class Citation(BaseModel):
    source: str
    gazette_id: str | None
    part: str | None
    section: str | None
    notification_date: str | None
    passage: str
    source_url: str | None


class HistoryTurn(BaseModel):
    question: str
    answer: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=50)  # [{"question": str, "answer": str}, ...] from the current session only


class AskResponse(BaseModel):
    answer: str
    refused: bool
    citations: list[Citation]
    disclaimer: str = "This is not legal advice — verify against the original Gazette."
