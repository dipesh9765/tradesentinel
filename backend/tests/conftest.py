import os
import pytest
import sqlite3

TEST_DB_PATH = os.path.join(os.path.dirname(__file__), "test_trading.db")
# Set immediately at module import time BEFORE any tests or modules are imported
os.environ["TRADING_DB_PATH"] = TEST_DB_PATH

@pytest.fixture(autouse=True, scope="session")
def setup_isolated_test_database():
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

    import database
    database.init_db()

    yield

    # Clean up test DB after test session
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass


@pytest.fixture(autouse=True)
def relaxed_trading_limits(monkeypatch):
    """Existing tests open many trades per day; the discipline limits have dedicated tests."""
    from config import settings
    monkeypatch.setattr(settings, "MAX_TRADES_PER_DAY", 1000)
    monkeypatch.setattr(settings, "MAX_CONSECUTIVE_LOSSES", 1000)
