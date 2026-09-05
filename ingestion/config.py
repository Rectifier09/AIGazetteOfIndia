# ingestion/config.py
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def get_connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)
