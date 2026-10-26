import pytest
from fastapi.testclient import TestClient

from app.core.security import ACTIVE_SESSIONS, create_session_token, invalidate_session_token
from app.db import database
from app.main import app
from app.market.market_data import market_data_manager
from app.trading.kite_executor import kite_executor

client = TestClient(app)


def test_kite_auth_guard_and_30s_verification():
    # 1. Clear sessions and lock vault
    conn = database.get_db_connection()
    conn.execute("DELETE FROM auth_config;")
    conn.execute("DELETE FROM secure_vault;")
    conn.commit()
    conn.close()
    database.lock_vault()
    ACTIVE_SESSIONS.clear()

    # 2. When system session does not exist, outgoing Kite request MUST BE BLOCKED
    with pytest.raises(PermissionError) as excinfo:
        kite_executor.verify_outgoing_kite_request()
    assert "No active authenticated system session exists" in str(excinfo.value)

    # 3. MarketDataManager's refresh_live_quotes returns False and logs blocked message
    assert market_data_manager.refresh_live_quotes() is False

    # 4. Initialize system with master password
    database.setup_master_password("MasterSafePassword123!")
    token = create_session_token()

    # 5. verify_auth_token_now() validates system session presence
    res = kite_executor.verify_auth_token_now()
    # Since no real Kite credentials have been added yet, it accurately catches missing token:
    assert res["valid"] is False
    assert "Kite access token missing" in res["error"]

    # 6. Test /api/auth/verify endpoint with valid bearer token
    verify_resp = client.get("/api/auth/verify", headers={"Authorization": f"Bearer {token}"})
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["authenticated"] is True
    assert v_data["session_valid"] is True
    assert "kite_token_check" in v_data

    # 7. Unauthenticated call to /api/auth/verify is rejected with 401
    bad_verify = client.get("/api/auth/verify")
    assert bad_verify.status_code == 401

    # 8. Clean up
    invalidate_session_token(token)
    database.lock_vault()
    conn = database.get_db_connection()
    conn.execute("DELETE FROM auth_config;")
    conn.execute("DELETE FROM secure_vault;")
    conn.commit()
    conn.close()
