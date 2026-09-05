# ingestion/tests/conftest.py
import pytest
from config import get_connection


@pytest.fixture
def db_conn():
    conn = get_connection()
    yield conn
    conn.execute("TRUNCATE notifications, relationships RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()
