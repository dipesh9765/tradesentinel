from fastapi.testclient import TestClient

from app.core.security import validate_session_token
from app.db import database
from app.main import app

client = TestClient(app)


def test_auth_lockdown_and_setup_flow():
    # 1. Clean DB auth
    conn = database.get_db_connection()
    conn.execute("DELETE FROM auth_config;")
    conn.execute("DELETE FROM secure_vault;")
    conn.commit()
    conn.close()
    database.lock_vault()

    # 2. Status when not initialized: should return is_initialized: False
    status_resp = client.get("/api/auth/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["is_initialized"] is False
    assert status_resp.json()["is_authenticated"] is False

    # 3. Accessing protected endpoint without setup returns 403
    unauth_resp = client.get("/api/status")
    assert unauth_resp.status_code == 403

    # 4. First-time setup: master password too short -> 400
    fail_setup = client.post("/api/auth/setup", json={"password": "123"})
    assert fail_setup.status_code == 400

    # 5. First-time setup: valid password -> 200 and returns session token
    setup_resp = client.post("/api/auth/setup", json={"password": "MasterSecurePassword123!"})
    assert setup_resp.status_code == 200
    token = setup_resp.json()["token"]
    assert token is not None
    assert validate_session_token(token) is True

    # 6. Auth status now shows initialized and authenticated
    auth_check = client.get("/api/auth/status", headers={"Authorization": f"Bearer {token}"})
    assert auth_check.status_code == 200
    assert auth_check.json()["is_initialized"] is True
    assert auth_check.json()["is_authenticated"] is True
    assert auth_check.json()["is_vault_unlocked"] is True

    # 7. Accessing protected endpoint WITH token -> 200 OK
    prot_resp = client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
    assert prot_resp.status_code == 200
    assert prot_resp.json()["status"] == "ONLINE"

    # 8. Attempting setup again fails -> 400
    setup_again = client.post("/api/auth/setup", json={"password": "AnotherPassword"})
    assert setup_again.status_code == 400

    # 9. Invalid login attempt -> 401
    bad_login = client.post("/api/auth/login", json={"password": "WrongPassword"})
    assert bad_login.status_code == 401

    # 10. Valid login attempt -> 200 with new session token
    good_login = client.post("/api/auth/login", json={"password": "MasterSecurePassword123!"})
    assert good_login.status_code == 200
    token2 = good_login.json()["token"]

    # 11. Test encrypted settings storage
    update_resp = client.post(
        "/api/settings",
        headers={"Authorization": f"Bearer {token2}"},
        json={
            "kite_api_key": "my-kite-api-key-999",
            "kite_api_secret": "my-kite-secret-888",
            "gemini_api_key": "my-gemini-ai-key-777",
        },
    )
    assert update_resp.status_code == 200

    # 12. Verify secrets in raw DB are encrypted
    conn = database.get_db_connection()
    vault_rows = conn.execute("SELECT key, encrypted_value FROM secure_vault").fetchall()
    conn.close()
    for row in vault_rows:
        # None of the plain text values should be visible in raw database
        assert "my-kite-api-key-999" not in row["encrypted_value"]
        assert "my-kite-secret-888" not in row["encrypted_value"]
        assert "my-gemini-ai-key-777" not in row["encrypted_value"]

    # 13. Get settings endpoint masks keys
    get_sett = client.get("/api/settings", headers={"Authorization": f"Bearer {token2}"})
    assert get_sett.status_code == 200
    s_data = get_sett.json()
    assert s_data["has_kite_api_key"] is True
    assert "my-kite-api-key-999" not in s_data["kite_api_key_preview"]
    assert "••••••••" in s_data["kite_api_key_preview"]

    # 14. Logout invalidates token
    logout_resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token2}"})
    assert logout_resp.status_code == 200

    # 15. Attempting to use logged-out token fails -> 401
    post_logout = client.get("/api/status", headers={"Authorization": f"Bearer {token2}"})
    assert post_logout.status_code == 401
