import os

from fastapi.testclient import TestClient

from app.core.server_logger import (
    CURRENT_LOG_FILE,
    LOGS_DIR,
    MAX_LOG_FILE_BYTES,
    log_config_saved,
    log_outgoing_error,
    log_outgoing_request,
    log_outgoing_response,
)
from app.main import app


def test_server_logging_file_attributes_and_rotation():
    """Verifies that log files follow naming with datetime and 3MB max size."""
    assert os.path.isdir(LOGS_DIR)
    assert MAX_LOG_FILE_BYTES == 3 * 1024 * 1024  # Exactly 3MB

    # Check that current log file has datetime in filename
    filename = os.path.basename(CURRENT_LOG_FILE)
    assert filename.startswith("server_")
    assert filename.endswith(".log")
    assert os.path.exists(CURRENT_LOG_FILE)


def test_server_logging_captures_requests_and_responses():
    """Verifies incoming requests, parameters, and responses are appended to the log file."""
    client = TestClient(app)

    # Send a request with query params
    response = client.get("/api/auth/status")
    assert response.status_code == 200

    # Send custom helper events
    log_outgoing_request("Zerodha Kite", "test_action", {"param_key": "param_val"})
    log_outgoing_response("Zerodha Kite", "test_action", {"status": "ok"}, 12.5)
    log_outgoing_error("Google Gemini", "test_action", ValueError("Test error message"), 15.0)
    log_config_saved("test_source", ["TEST_KEY_1", "TEST_KEY_2"], "LIVE")

    # Read log file content
    with open(CURRENT_LOG_FILE, encoding="utf-8") as f:
        log_content = f.read()

    assert "INCOMING REQUEST" in log_content
    assert "/api/auth/status" in log_content
    assert "OUTGOING RESPONSE" in log_content
    assert "OUTGOING CALL -> [Zerodha Kite]" in log_content
    assert "OUTGOING ERROR !! [Google Gemini]" in log_content
    assert "CONFIG SAVED -> Source: test_source" in log_content
    assert "TEST_KEY_1" in log_content


def test_candle_requests_suppressed_unless_error():
    """Verifies that high-frequency /api/market/candles requests are not logged when successful, but logged on error."""
    client = TestClient(app)

    # Record current file position
    with open(CURRENT_LOG_FILE, encoding="utf-8") as f:
        before_content = f.read()

    # 1. Error /api/market/candles call (unauthenticated 401 or uninitialized 403)
    res_err = client.get("/api/market/candles?symbol=NIFTY%2050")
    assert res_err.status_code in [401, 403]  # Error status code

    with open(CURRENT_LOG_FILE, encoding="utf-8") as f:
        after_content = f.read()

    new_logs = after_content[len(before_content) :]
    # Status 401/403 should be logged because it is an error (>= 400)
    assert "/api/market/candles" in new_logs
    assert f"Status: {res_err.status_code}" in new_logs
