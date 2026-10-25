/**
 * Centralized General Constants (GenConsts) - TradeSentinel Frontend.
 * Eliminates magic strings, hardcoded numbers, and scattered configuration keys.
 */
export const GenConsts = {
    // Session & LocalStorage Keys
    STORAGE_KEYS: {
        AUTH_TOKEN: "tradesentinel_auth_token",
        OFFICE_MODE: "tradesentinel_office_mode",
    },

    // Authentication States
    AUTH_STATES: {
        CHECKING: "CHECKING",
        UNINITIALIZED: "UNINITIALIZED",
        UNAUTHENTICATED: "UNAUTHENTICATED",
        AUTHENTICATED: "AUTHENTICATED",
    },

    // WebSocket Events
    WS_EVENTS: {
        TICK: "TICK",
        INIT: "INIT",
        TRADE_PROPOSAL_ALERT: "TRADE_PROPOSAL_ALERT",
        ORDER_UPDATE: "ORDER_UPDATE",
        POSITION_UPDATE: "POSITION_UPDATE",
        PING: "PING",
        PONG: "PONG",
    },

    // Timeouts and Polling Intervals (Milliseconds)
    INTERVALS: {
        KITE_VERIFY_MS: 30000,
        CANDLE_POLL_MS: 4000,
        NOTIFICATION_AUTO_CLOSE_MS: 5000,
        TOOLTIP_DELAY_MS: 200,
    },

    // Market Data & Chart Statuses
    CHART_STATUSES: {
        OK: "OK",
        NO_DATA: "NO_DATA",
        CONFIG_REQUIRED: "CONFIG_REQUIRED",
        KITE_BROKER_ERROR: "KITE_BROKER_ERROR",
    },

    // Trading Modes
    MODES: {
        PAPER: "PAPER",
        LIVE: "LIVE",
    },

    // Order & Position Statuses
    STATUSES: {
        OPEN: "OPEN",
        CLOSED: "CLOSED",
        PENDING_APPROVAL: "PENDING_APPROVAL",
        REJECTED: "REJECTED",
        EXECUTED: "EXECUTED",
        CANCELLED: "CANCELLED",
    },

    // Trade Signals
    SIGNALS: {
        BUY_CALL: "BUY_CALL",
        BUY_PUT: "BUY_PUT",
        BUY_EQUITY: "BUY_EQUITY",
        SHORT_EQUITY: "SHORT_EQUITY",
    },

    // Market Direction Bias
    DIRECTIONS: {
        BULLISH: "BULLISH",
        BEARISH: "BEARISH",
    },

    // Product Types
    PRODUCTS: {
        MIS: "MIS",
        CNC: "CNC",
    },

    // API Routes
    API_ROUTES: {
        AUTH_STATUS: "/api/auth/status",
        AUTH_SETUP: "/api/auth/setup",
        AUTH_LOGIN: "/api/auth/login",
        AUTH_LOGOUT: "/api/auth/logout",
        AUTH_VERIFY: "/api/auth/verify",
        STATUS: "/api/status",
        MARKET_QUOTES: "/api/market/quotes",
        MARKET_CANDLES: "/api/market/candles",
        AI_SCAN: "/api/ai/scan",
        TRADES_APPROVE: "/api/trades/approve",
        TRADES_REJECT: "/api/trades/reject",
        TRADES_POSITIONS: "/api/trades/positions",
        TRADES_ORDERS: "/api/trades/orders",
        TRADES_HISTORY: "/api/trades/history",
        TRADES_CLOSE_POSITION: "/api/trades/close-position",
        SETTINGS: "/api/settings",
        SETTINGS_VAULT: "/api/settings/vault",
        SETTINGS_TRADING_MODE: "/api/settings/trading-mode",
        SETTINGS_TEST_NOTIFICATIONS: "/api/settings/notifications/test",
    },
} as const;

export type AuthStateType = typeof GenConsts.AUTH_STATES[keyof typeof GenConsts.AUTH_STATES];
export type ChartStatusType = typeof GenConsts.CHART_STATUSES[keyof typeof GenConsts.CHART_STATUSES];
export type TradingModeType = typeof GenConsts.MODES[keyof typeof GenConsts.MODES];
export type OrderStatusType = typeof GenConsts.STATUSES[keyof typeof GenConsts.STATUSES];
export type SignalType = typeof GenConsts.SIGNALS[keyof typeof GenConsts.SIGNALS];
export type MarketDirectionType = typeof GenConsts.DIRECTIONS[keyof typeof GenConsts.DIRECTIONS];
