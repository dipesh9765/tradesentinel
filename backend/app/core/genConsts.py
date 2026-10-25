"""
Centralized General Constants (GenConsts) - KitePulse AI Backend.
Eliminates hardcoded strings, magic numbers, and duplicate values across the application.
"""

from typing import Final


class GenConsts:
    """Central constants namespace for KitePulse AI backend."""

    # Application Metadata
    APP_NAME: Final[str] = "KitePulse AI"
    APP_VERSION: Final[str] = "1.0.0"

    # Filesystem & Database
    DB_NAME: Final[str] = "trading.db"
    INSTRUMENTS_FILE_NAME: Final[str] = "instruments.json"

    # API Routes & Headers
    API_V1_PREFIX: Final[str] = "/api"
    WS_LIVE_PATH: Final[str] = "/ws/live"
    AUTH_HEADER: Final[str] = "Authorization"
    BEARER_PREFIX: Final[str] = "Bearer "

    # Trading Execution Parameters
    DEFAULT_LOT_SIZE: Final[int] = 1
    MAX_LOT_SIZE: Final[int] = 1
    DEFAULT_PRODUCT: Final[str] = "MIS"  # Intraday
    PRODUCT_CNC: Final[str] = "CNC"      # Delivery
    INITIAL_PAPER_CAPITAL: Final[float] = 100000.0
    MAX_DAILY_LOSS_LIMIT: Final[float] = 2000.0  # Max daily loss circuit breaker
    MIN_CONFLUENCE_THRESHOLD: Final[int] = 75    # Minimum score for A+ setup generation

    # Trading Modes
    MODE_PAPER: Final[str] = "PAPER"
    MODE_LIVE: Final[str] = "LIVE"

    # Instrument Classifications
    TYPE_INDEX: Final[str] = "INDEX"
    TYPE_EQUITY: Final[str] = "EQUITY"

    # Order & Position Statuses
    STATUS_OPEN: Final[str] = "OPEN"
    STATUS_CLOSED: Final[str] = "CLOSED"
    STATUS_PENDING_APPROVAL: Final[str] = "PENDING_APPROVAL"
    STATUS_REJECTED: Final[str] = "REJECTED"
    STATUS_EXECUTED: Final[str] = "EXECUTED"
    STATUS_CANCELLED: Final[str] = "CANCELLED"

    # Trade Signal Types
    SIGNAL_BUY_CALL: Final[str] = "BUY_CALL"
    SIGNAL_BUY_PUT: Final[str] = "BUY_PUT"
    SIGNAL_BUY_EQUITY: Final[str] = "BUY_EQUITY"
    SIGNAL_SHORT_EQUITY: Final[str] = "SHORT_EQUITY"

    # Market Directions
    DIRECTION_BULLISH: Final[str] = "BULLISH"
    DIRECTION_BEARISH: Final[str] = "BEARISH"

    # WebSocket Event Types
    WS_EVENT_TICK: Final[str] = "TICK"
    WS_EVENT_INIT: Final[str] = "INIT"
    WS_EVENT_PROPOSAL_ALERT: Final[str] = "TRADE_PROPOSAL_ALERT"
    WS_EVENT_ORDER_UPDATE: Final[str] = "ORDER_UPDATE"
    WS_EVENT_POSITION_UPDATE: Final[str] = "POSITION_UPDATE"
    WS_EVENT_PING: Final[str] = "PING"
    WS_EVENT_PONG: Final[str] = "PONG"

    # Intervals & Timeouts (Seconds)
    KITE_TOKEN_CHECK_INTERVAL_SEC: Final[int] = 30
    MARKET_TICK_STREAM_INTERVAL_SEC: Final[int] = 2
    TOKEN_EXPIRY_HOURS: Final[int] = 24
    DB_LOCK_TIMEOUT_SEC: Final[int] = 10

    # Market Data & Chart Statuses
    CHART_STATUS_OK: Final[str] = "OK"
    CHART_STATUS_NO_DATA: Final[str] = "NO_DATA"
    CHART_STATUS_CONFIG_REQUIRED: Final[str] = "CONFIG_REQUIRED"
    CHART_STATUS_BROKER_ERROR: Final[str] = "KITE_BROKER_ERROR"
