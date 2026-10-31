import datetime
import json
import logging
import os
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from app.core.config import BASE_DIR

# Setup logs directory inside backend
LOGS_DIR = str(BASE_DIR / "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# 3MB per file
MAX_LOG_FILE_BYTES = 3 * 1024 * 1024  # Exactly 3MB

# Generate filename with date and time
current_timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
CURRENT_LOG_FILE = os.path.join(LOGS_DIR, f"server_{current_timestamp_str}.log")

# Sensitive keys to mask in logs
SENSITIVE_KEYS = {
    "password",
    "pass",
    "pwd",
    "secret",
    "api_key",
    "api_secret",
    "access_token",
    "request_token",
    "authorization",
    "token",
    "master_password",
    "master_key_salt",
    "encrypted_value",
    "credentials",
}


def mask_sensitive_data(data: Any) -> Any:
    """Recursively masks passwords, tokens, and API secrets to avoid log exposure."""
    if isinstance(data, dict):
        masked = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS:
                masked[k] = "***MASKED***"
            elif isinstance(v, (dict, list)):
                masked[k] = mask_sensitive_data(v)
            else:
                masked[k] = v
        return masked
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    return data


def setup_server_logging():
    """Initializes standard rotating 3MB file logger with date and time in filename."""
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] [%(name)s:%(lineno)d] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. 3MB Rotating File Handler
    file_handler = RotatingFileHandler(
        CURRENT_LOG_FILE, maxBytes=MAX_LOG_FILE_BYTES, backupCount=50, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # 2. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    # 3. Configure Root Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if re-initialized
    if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
        root_logger.addHandler(file_handler)
    if not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in root_logger.handlers
    ):
        root_logger.addHandler(console_handler)

    # Also route uvicorn loggers to file
    for uvi_logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"]:
        uvi_logger = logging.getLogger(uvi_logger_name)
        uvi_logger.setLevel(logging.INFO)
        if not any(isinstance(h, RotatingFileHandler) for h in uvi_logger.handlers):
            uvi_logger.addHandler(file_handler)

    root_logger.info("=" * 70)
    root_logger.info("SERVER LOGGING INITIALIZED")
    root_logger.info(f"Log File: {CURRENT_LOG_FILE}")
    root_logger.info("Max File Size: 3MB (Rotating)")
    root_logger.info("=" * 70)

    return root_logger


# Dedicated logger instance for server activity
server_log = logging.getLogger("server")


class RequestResponseLoggingMiddleware(BaseHTTPMiddleware):
    """
    Standard production middleware:
    Logs every incoming request, parameters, payload, latency, response code, and payload.
    """

    async def dispatch(self, request: Request, call_next):
        req_id = uuid.uuid4().hex[:8].upper()
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"
        method = request.method
        url_path = request.url.path
        query_params = dict(request.query_params)

        # Sanitize query parameters
        masked_query = mask_sensitive_data(query_params)

        # Read and sanitize request body if present
        body_text = ""
        try:
            body_bytes = await request.body()
            if body_bytes:
                try:
                    parsed_json = json.loads(body_bytes.decode("utf-8"))
                    body_text = json.dumps(mask_sensitive_data(parsed_json))
                except Exception:
                    body_text = f"<{len(body_bytes)} raw bytes>"
            # Restore request body for subsequent route handlers
            request._body = body_bytes
        except Exception as e:
            body_text = f"<unreadable: {e}>"

        is_candle_req = url_path.startswith("/api/market/candles")

        # Skip logging normal incoming high-frequency candle polling
        if not is_candle_req:
            server_log.info(
                f"INCOMING REQUEST [{req_id}] -> {method} {url_path} "
                f"| Client: {client_ip} "
                f"| Params: {masked_query if masked_query else 'None'} "
                f"| Body: {body_text if body_text else 'Empty'}"
            )

        try:
            response = await call_next(request)
            duration_ms = round((time.time() - start_time) * 1000, 2)

            # High-frequency candle requests: Do not log successful requests/responses unless there is an error
            if is_candle_req and response.status_code < 400:
                return response

            # For streaming or large responses, preview content without breaking stream
            resp_body_preview = ""
            if isinstance(response, Response) and not isinstance(response, StreamingResponse):
                try:
                    # Only read small JSON responses
                    content_type = response.headers.get("content-type", "")
                    if (
                        "application/json" in content_type
                        and hasattr(response, "body")
                        and response.body
                        and len(response.body) < 4096
                    ):
                        parsed_resp = json.loads(bytes(response.body).decode("utf-8"))
                        resp_body_preview = f"| Response: {json.dumps(mask_sensitive_data(parsed_resp))}"
                except Exception:
                    pass

            level = logging.WARNING if response.status_code >= 400 else logging.INFO
            server_log.log(
                level,
                f"OUTGOING RESPONSE [{req_id}] <- {method} {url_path} "
                f"| Status: {response.status_code} "
                f"| Duration: {duration_ms}ms "
                f"{resp_body_preview}",
            )
            return response

        except Exception as exc:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            server_log.error(
                f"SERVER ERROR [{req_id}] !! {method} {url_path} "
                f"| Duration: {duration_ms}ms "
                f"| Error: {type(exc).__name__}: {exc!s}",
                exc_info=True,
            )
            raise exc


# Outgoing request & configuration logging helpers
def log_outgoing_request(service: str, action: str, params: dict[str, Any] | None = None):
    """Logs outgoing calls to external services like Zerodha Kite or Google Gemini."""
    masked_params = mask_sensitive_data(params) if params else {}
    server_log.info(f"OUTGOING CALL -> [{service}] Action: {action} | Params: {masked_params}")


def log_outgoing_response(service: str, action: str, summary: Any, duration_ms: float):
    """Logs the response received from external services."""
    masked_summary = mask_sensitive_data(summary) if isinstance(summary, (dict, list)) else summary
    server_log.info(
        f"OUTGOING RESPONSE <- [{service}] Action: {action} | Duration: {duration_ms}ms | Result: {masked_summary}"
    )


def log_outgoing_error(service: str, action: str, error: Exception, duration_ms: float):
    """Logs any error from outgoing external service calls."""
    server_log.error(
        f"OUTGOING ERROR !! [{service}] Action: {action} | Duration: {duration_ms}ms | Error: {type(error).__name__}: {error!s}"
    )


def log_config_saved(source: str, keys_modified: list, mode: str | None = None):
    """Logs configuration changes and settings updates."""
    mode_info = f" | Mode: {mode}" if mode else ""
    server_log.info(f"CONFIG SAVED -> Source: {source} | Keys Modified: {keys_modified}{mode_info}")
