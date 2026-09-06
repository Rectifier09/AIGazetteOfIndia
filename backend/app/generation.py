from google import genai
from app.config import GEMINI_API_KEY
from app.models import AskResponse, Citation

_client = genai.Client(api_key=GEMINI_API_KEY)

GENERATION_MODEL = "gemini-flash-latest"
MIN_RELEVANCE_SCORE = 0.0  # tune from eval results (Task 6) — do not guess a value here

REFUSAL_MESSAGE = (
    "I couldn't find a notification matching this in the sources I cover "
    "(Central Gazette + Gujarat Gazette, Labour Codes only). I can answer "
    "questions about Code on Wages, Industrial Relations Code, OSH Code, "
    "and Code on Social Security — as notified centrally or in Gujarat."
)


def _build_prompt(question: str, passages: list[dict], history: list[dict]) -> str:
    history_block = "\n".join(f"Q: {h['question']}\nA: {h['answer']}" for h in history)
    passages_block = "\n\n".join(
        f"[Passage {i + 1}] Source: {p['source']}, Gazette ID: {p['gazette_id']}, "
        f"Part: {p['part']}, Date: {p['notification_date']}\n{p['operative_text']}"
        for i, p in enumerate(passages)
    )
    return (
        "You answer questions about Indian Labour Codes using ONLY the passages below. "
        "Never use outside knowledge. Be concise and plain-language.\n\n"
        f"Prior conversation (may be empty):\n{history_block}\n\n"
        f"Passages:\n{passages_block}\n\n"
        f"Question: {question}\n"
        "Answer:"
    )


def generate_answer(question: str, passages: list[dict], history: list[dict]) -> AskResponse:
    relevant = [p for p in passages if p.get("score", 0.0) >= MIN_RELEVANCE_SCORE]
    if not relevant:
        return AskResponse(answer=REFUSAL_MESSAGE, refused=True, citations=[])

    prompt = _build_prompt(question, relevant, history)
    response = _client.models.generate_content(model=GENERATION_MODEL, contents=prompt)

    citations = [
        Citation(
            source=p["source"], gazette_id=p["gazette_id"], part=p["part"], section=p["section"],
            notification_date=p["notification_date"], passage=p["operative_text"],
            source_url=p["source_url"],
        )
        for p in relevant
    ]
    return AskResponse(answer=response.text, refused=False, citations=citations)
