import pytest
from fastapi.testclient import TestClient

from app.core.security import create_session_token, invalidate_session_token
from app.db import database
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_auth_fixture():
    # Setup master password and create token for API tests
    if not database.is_master_password_set():
        database.setup_master_password("TestMasterKey123!")
    token = create_session_token()
    yield token
    invalidate_session_token(token)


def test_api_status(setup_auth_fixture):
    token = setup_auth_fixture
    response = client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ONLINE"
    assert "portfolio" in data


def test_api_quotes(setup_auth_fixture):
    token = setup_auth_fixture
    response = client.get("/api/market/quotes", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    quotes = response.json()
    assert len(quotes) >= 1
    symbols = [q["symbol"] for q in quotes]
    assert "BANK NIFTY" in symbols


def test_api_candles_unconfigured(setup_auth_fixture):
    token = setup_auth_fixture
    response = client.get("/api/market/candles?symbol=NIFTY 50", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "NIFTY 50"
    # When unconfigured, does not fabricate dummy candles
    assert isinstance(data["candles"], list)


def test_ai_scan_requires_kite_connection(setup_auth_fixture):
    token = setup_auth_fixture
    # Without real Kite connection, scan should block with 400
    scan_resp = client.post(
        "/api/ai/scan", headers={"Authorization": f"Bearer {token}"}, json={"symbol": "NIFTY 50"}
    )
    assert scan_resp.status_code == 400
    assert "Zerodha Kite Connect is not configured" in scan_resp.json()["detail"]


def test_ai_scan_defaults_to_first_watchlist_symbol(setup_auth_fixture, monkeypatch):
    """Regression: an omitted symbol must fall back to the watchlist, not be passed on as None."""
    from app.api.v1.endpoints import trades
    from app.core.config import get_watchlist_symbols

    seen = {}
    monkeypatch.setattr(trades.kite_executor, "api_key", "k")
    monkeypatch.setattr(trades.kite_executor, "access_token", "t")
    monkeypatch.setattr(trades.market_data_manager, "get_quote", lambda s: seen.setdefault("quote", s) and {})
    monkeypatch.setattr(
        trades.trade_analyzer,
        "analyze_market_setup",
        lambda s, q, df: seen.setdefault("analyze", s) and {"actionable": False, "reason": "x"},
    )
    resp = client.post("/api/ai/scan", headers={"Authorization": f"Bearer {setup_auth_fixture}"}, json={})
    assert resp.status_code == 409
    assert seen["quote"] == seen["analyze"] == get_watchlist_symbols()[0]
