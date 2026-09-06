# backend/eval/run_eval.py
import json
import sys
import time
from pathlib import Path
import requests

API_URL = "http://localhost:8000"
QUESTIONS_FILE = Path(__file__).parent / "questions.md"
RESULTS_FILE = Path(__file__).parent.parent / "eval_results.json"
MAX_RETRIES = 5


def load_questions() -> list[str]:
    lines = QUESTIONS_FILE.read_text().splitlines()
    return [
        line.split(".", 1)[1].strip()
        for line in lines
        if line and line[0].isdigit() and "." in line
    ]


def ask_with_retry(question: str) -> dict:
    # Gemini's free tier intermittently returns 503 "high demand" under real
    # load — this is transient upstream capacity, not a bug in this service,
    # so a short retry-with-backoff here (not in the reviewed API code) is
    # the right place to absorb it for a manual eval run.
    for attempt in range(1, MAX_RETRIES + 1):
        response = requests.post(f"{API_URL}/ask", json={"question": question, "history": []})
        if response.status_code < 500 or attempt == MAX_RETRIES:
            response.raise_for_status()
            return response.json()
        wait = 2 ** attempt
        print(f"  ({response.status_code}, retrying in {wait}s — attempt {attempt}/{MAX_RETRIES})")
        time.sleep(wait)


def main():
    questions = load_questions()
    results = []
    if RESULTS_FILE.exists():
        # Resume: skip questions already answered in a prior (partial) run,
        # so a retried invocation doesn't re-spend quota on successes.
        results = json.loads(RESULTS_FILE.read_text())
        done = {r["question"] for r in results}
        questions = [q for q in questions if q not in done]
        if done:
            print(f"Resuming — {len(done)} already answered, {len(questions)} remaining.")

    for question in questions:
        body = ask_with_retry(question)
        results.append({"question": question, **body})
        print(f"\nQ: {question}")
        print(f"Refused: {body['refused']}")
        print(f"A: {body['answer']}")
        for citation in body["citations"]:
            print(f"  Cite: {citation['gazette_id']} / {citation['part']} / {citation['notification_date']}")
        # Write incrementally so a late failure doesn't lose earlier answers.
        RESULTS_FILE.write_text(json.dumps(results, indent=2))

    print(f"\nWrote {RESULTS_FILE} — check each answer against the source PDF manually.")


if __name__ == "__main__":
    sys.exit(main())
