import pytest
from fastapi.testclient import TestClient
import database
from security import create_session_token, invalidate_session_token
from main import app
from config import settings
from kite_executor import kite_executor
from market_data import market_data_manager

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
    scan_resp = client.post("/api/ai/scan", headers={"Authorization": f"Bearer {token}"}, json={"symbol": "NIFTY 50"})
    assert scan_resp.status_code == 400
    assert "Zerodha Kite Connect is not configured" in scan_resp.json()["detail"]
