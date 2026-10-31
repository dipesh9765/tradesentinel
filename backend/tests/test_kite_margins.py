from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_session_token, invalidate_session_token
from app.db import database
from app.main import app
from app.trading.engine import trading_engine

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_auth_fixture():
    if not database.is_master_password_set():
        database.setup_master_password("TestMasterKey123!")
    token = create_session_token()
    yield token
    invalidate_session_token(token)


def test_get_kite_balance_unauthenticated(setup_auth_fixture):
    token = setup_auth_fixture
    # When kite is not connected / no access token
    trading_engine.access_token = ""
    trading_engine.kite_engine.access_token = ""

    response = client.get("/api/kite/balance", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is False
    assert "not connected" in data["error"].lower()


def test_get_kite_balance_success(setup_auth_fixture, monkeypatch):
    token = setup_auth_fixture

    # Mock kite_client and session
    mock_kite = MagicMock()
    mock_kite.margins.return_value = {
        "equity": {
            "enabled": True,
            "net": 125500.50,
            "available": {
                "cash": 125500.50,
                "opening_balance": 130000.00,
                "live_balance": 120500.50,
                "collateral": 0.0,
                "intraday_payin": 0.0,
            },
            "utilised": {"debits": 5000.00, "span": 0.0, "exposure": 0.0},
        },
        "commodity": {
            "enabled": False,
            "net": 0.0,
            "available": {"live_balance": 0.0, "cash": 0.0},
            "utilised": {"debits": 0.0},
        },
    }

    trading_engine.access_token = "mock_access_token_123"
    trading_engine.kite_engine.access_token = "mock_access_token_123"
    trading_engine.kite_engine.kite_client = mock_kite

    # Monkeypatch verify_outgoing_kite_request to bypass remote ping in tests
    monkeypatch.setattr(trading_engine.kite_engine, "verify_outgoing_kite_request", lambda: True)
    monkeypatch.setattr(trading_engine, "is_authenticated", lambda: True)

    response = client.get("/api/kite/balance", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert "equity" in data
    assert data["equity"]["available_cash"] == 120500.50
    assert data["equity"]["net"] == 125500.50
    assert data["equity"]["utilised"] == 5000.00
    assert data["equity"]["opening_balance"] == 130000.00
    assert "timestamp" in data
