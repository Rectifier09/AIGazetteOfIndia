import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def get_connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, connect_timeout=10)
