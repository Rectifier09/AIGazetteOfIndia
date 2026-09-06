from pydantic import BaseModel


class Citation(BaseModel):
    source: str
    gazette_id: str | None
    part: str | None
    section: str | None
    notification_date: str | None
    passage: str
    source_url: str | None


class AskRequest(BaseModel):
    question: str
    history: list[dict] = []  # [{"question": str, "answer": str}, ...] from the current session only


class AskResponse(BaseModel):
    answer: str
    refused: bool
    citations: list[Citation]
    disclaimer: str = "This is not legal advice — verify against the original Gazette."
