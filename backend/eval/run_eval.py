# backend/eval/run_eval.py
import json
import sys
from pathlib import Path
import requests

API_URL = "http://localhost:8000"
QUESTIONS_FILE = Path(__file__).parent / "questions.md"


def load_questions() -> list[str]:
    lines = QUESTIONS_FILE.read_text().splitlines()
    return [
        line.split(".", 1)[1].strip()
        for line in lines
        if line and line[0].isdigit() and "." in line
    ]


def main():
    questions = load_questions()
    results = []
    for question in questions:
        response = requests.post(f"{API_URL}/ask", json={"question": question, "history": []})
        response.raise_for_status()
        body = response.json()
        results.append({"question": question, **body})
        print(f"\nQ: {question}")
        print(f"Refused: {body['refused']}")
        print(f"A: {body['answer']}")
        for citation in body["citations"]:
            print(f"  Cite: {citation['gazette_id']} / {citation['part']} / {citation['notification_date']}")

    Path("eval_results.json").write_text(json.dumps(results, indent=2))
    print("\nWrote eval_results.json — check each answer against the source PDF manually.")


if __name__ == "__main__":
    sys.exit(main())
