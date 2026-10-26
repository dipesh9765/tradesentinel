import type { Quote, Candle, TradeProposal, Position, OrderRecord, PortfolioSummary, HistoryItem, KiteBalance } from "../types";
import { GenConsts } from "../constants";

const CURRENT_HOST = typeof window !== "undefined" && window.location ? (window.location.hostname || "127.0.0.1") : "127.0.0.1";
// VITE_API_BASE_URL overrides the backend origin. Set it to an empty string for same-origin deployments
// (e.g. behind the bundled nginx proxy); when unset, the dev default is the current host on port 8000.
const configuredBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
const API_BASE = configuredBase !== undefined ? configuredBase.replace(/\/$/, "") : `http://${CURRENT_HOST}:8000`;
const TOKEN_KEY = GenConsts.STORAGE_KEYS.AUTH_TOKEN;

let onUnauthorizedCallback: (() => void) | null = null;

export function setOnUnauthorized(callback: () => void) {
  onUnauthorizedCallback = callback;
}

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function authFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const token = getAuthToken();
  const headers = new Headers(init.headers || {});
  
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(input, { ...init, headers });

  if (response.status === 401) {
    clearAuthToken();
    if (onUnauthorizedCallback) {
      onUnauthorizedCallback();
    }
  }

  return response;
}

// ==================== AUTHENTICATION APIS ====================

export interface AuthStatus {
  is_initialized: boolean;
  is_authenticated: boolean;
  is_vault_unlocked: boolean;
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  const res = await authFetch(`${API_BASE}/api/auth/status`);
  if (!res.ok) throw new Error("Failed to check auth status");
  return res.json();
}

export async function verifyAuthTokenApi(): Promise<{
  authenticated: boolean;
  session_valid: boolean;
  kite_token_check: any;
}> {
  const res = await authFetch(`${API_BASE}/api/auth/verify`);
  if (!res.ok) throw new Error("Authentication verification failed");
  return res.json();
}

export async function setupMasterPasswordApi(password: string): Promise<{ success: boolean; token: string; message: string }> {
  const res = await fetch(`${API_BASE}/api/auth/setup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to setup master password");
  }
  const data = await res.json();
  if (data.token) {
    setAuthToken(data.token);
  }
  return data;
}

export async function loginMasterPasswordApi(password: string): Promise<{ success: boolean; token: string; message: string }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Invalid master password");
  }
  const data = await res.json();
  if (data.token) {
    setAuthToken(data.token);
  }
  return data;
}

export async function logoutApi(): Promise<void> {
  try {
    await authFetch(`${API_BASE}/api/auth/logout`, { method: "POST" });
  } finally {
    clearAuthToken();
    if (onUnauthorizedCallback) {
      onUnauthorizedCallback();
    }
  }
}

// ==================== APPLICATION APIS ====================

export async function fetchStatus(): Promise<{
  status: string;
  app_name: string;
  mode: "PAPER" | "LIVE";
  gemini_active: boolean;
  kite_active: boolean;
  is_market_live: boolean;
  market_status_message: string;
  portfolio: PortfolioSummary;
}> {
  const res = await authFetch(`${API_BASE}/api/status`);
  if (!res.ok) throw new Error("Failed to fetch system status");
  return res.json();
}

export async function fetchQuotes(): Promise<Quote[]> {
  const res = await authFetch(`${API_BASE}/api/market/quotes`);
  if (!res.ok) throw new Error("Failed to fetch market quotes");
  return res.json();
}

export interface CandleResponse {
  symbol: string;
  candles: Candle[];
  status: "OK" | "KITE_SESSION_NOT_INITIALIZED" | "KITE_BROKER_ERROR" | "NO_DATA";
  message?: string;
  error_detail?: string | null;
  is_configured?: boolean;
}

export async function fetchCandles(symbol: string): Promise<CandleResponse> {
  const res = await authFetch(`${API_BASE}/api/market/candles?symbol=${encodeURIComponent(symbol)}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    return {
      symbol,
      candles: [],
      status: "KITE_BROKER_ERROR",
      message: err.detail || "Failed to fetch candle data from backend",
      error_detail: err.detail
    };
  }
  const data = await res.json();
  return {
    symbol: data.symbol || symbol,
    candles: data.candles || [],
    status: data.status || (data.candles && data.candles.length > 0 ? "OK" : "NO_DATA"),
    message: data.message,
    error_detail: data.error_detail,
    is_configured: data.is_configured
  };
}

export async function requestAiScan(symbol: string): Promise<TradeProposal> {
  const res = await authFetch(`${API_BASE}/api/ai/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "AI market scan failed");
  }
  const data = await res.json();
  return data.proposal || data;
}

export async function approveTradeApi(proposalId: string): Promise<any> {
  const res = await authFetch(`${API_BASE}/api/trades/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ proposal_id: proposalId })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to approve trade");
  }
  return res.json();
}

export async function rejectTradeApi(proposalId: string, reason = "User declined"): Promise<any> {
  const res = await authFetch(`${API_BASE}/api/trades/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ proposal_id: proposalId, reason })
  });
  if (!res.ok) throw new Error("Failed to reject trade");
  return res.json();
}

export async function fetchPositions(): Promise<{ positions: Position[]; summary: PortfolioSummary }> {
  const res = await authFetch(`${API_BASE}/api/positions`);
  if (!res.ok) throw new Error("Failed to fetch active positions");
  return res.json();
}

export async function closePositionApi(positionId: string): Promise<any> {
  const res = await authFetch(`${API_BASE}/api/positions/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ position_id: positionId })
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.detail || "Failed to close position");
  }
  return res.json();
}

export async function fetchOrders(): Promise<OrderRecord[]> {
  const res = await authFetch(`${API_BASE}/api/orders`);
  if (!res.ok) throw new Error("Failed to fetch order history");
  return res.json();
}

export async function updateSettingsApi(payload: {
  kite_api_key?: string;
  kite_api_secret?: string;
  kite_access_token?: string;
  gemini_api_key?: string;
  trading_mode?: string;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  discord_webhook_url?: string;
  slack_webhook_url?: string;
  office_mode?: boolean;
}): Promise<any> {
  const res = await authFetch(`${API_BASE}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error("Failed to update settings");
  return res.json();
}

export async function updateTradingModeApi(trading_mode: "PAPER" | "LIVE"): Promise<any> {
  const res = await authFetch(`${API_BASE}/api/settings/mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trading_mode })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to switch trading mode");
  }
  return res.json();
}

export async function fetchSettingsApi(): Promise<any> {
  const res = await authFetch(`${API_BASE}/api/settings`);
  if (!res.ok) throw new Error("Failed to load settings");
  return res.json();
}

export async function testNotificationApi(): Promise<any> {
  const res = await authFetch(`${API_BASE}/api/notifications/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" }
  });
  if (!res.ok) throw new Error("Failed to send test notification");
  return res.json();
}

export async function fetchHistory(limit: number = 50): Promise<HistoryItem[]> {
  const res = await authFetch(`${API_BASE}/api/history?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch trade suggestions history");
  return res.json();
}

export async function fetchKiteLoginUrl(): Promise<string> {
  const res = await authFetch(`${API_BASE}/api/kite/login-url`);
  if (!res.ok) throw new Error("Failed to get Kite login URL");
  const data = await res.json();
  return data.login_url;
}

export function extractRequestToken(rawInput: string): string {
  if (!rawInput) return "";
  const trimmed = rawInput.trim();
  if (trimmed.includes("request_token=")) {
    try {
      const url = trimmed.startsWith("http") ? new URL(trimmed) : new URL("http://localhost/?" + trimmed);
      return url.searchParams.get("request_token") || trimmed;
    } catch {
      const match = trimmed.match(/request_token=([a-zA-Z0-9_-]+)/);
      return match ? match[1] : trimmed;
    }
  }
  return trimmed;
}

export async function generateKiteSessionApi(requestToken: string): Promise<any> {
  const token = extractRequestToken(requestToken);
  const res = await authFetch(`${API_BASE}/api/kite/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_token: token })
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to generate Kite daily session. Check your token or API secret.");
  }
  return res.json();
}

export async function fetchKiteBalanceApi(): Promise<KiteBalance> {
  const res = await authFetch(`${API_BASE}/api/kite/balance`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to fetch Zerodha Kite account balance");
  }
  return res.json();
}


export function subscribeToLiveTicks(onMessage: (data: any) => void): () => void {
  let ws: WebSocket | null = null;
  let isClosed = false;

  function connect() {
    const token = getAuthToken();
    if (!token) return;

    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = API_BASE ? new URL(API_BASE).host : window.location.host;
    const wsUrl = `${wsProtocol}//${wsHost}/ws/live?token=${encodeURIComponent(token)}`;
    ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        onMessage(payload);
      } catch (e) {
        console.error("Failed to parse websocket message:", e);
      }
    };

    ws.onclose = (event) => {
      if (event.code === 4401) {
        // Unauthorized
        clearAuthToken();
        if (onUnauthorizedCallback) onUnauthorizedCallback();
        return;
      }
      if (!isClosed) {
        setTimeout(connect, 3000); // Auto reconnect
      }
    };

    ws.onerror = (err) => {
      console.warn("WebSocket feed notice:", err);
      ws?.close();
    };
  }

  connect();

  return () => {
    isClosed = true;
    ws?.close();
  };
}

export interface AIProviderInfo {
  id: string;
  label: string;
  models: string[];
  model: string;
  has_key: boolean;
  key_preview: string;
  key_url: string;
  key_hint: string;
}

export interface AIConfig {
  active_provider: string;
  providers: AIProviderInfo[];
}

async function aiRequest(path: string, payload?: object): Promise<any> {
  const res = await authFetch(`${API_BASE}${path}`, payload ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  } : undefined);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "AI provider request failed");
  return data;
}

export const fetchAIConfigApi = (): Promise<AIConfig> => aiRequest("/api/ai/config");

export const saveAIConfigApi = (payload: {
  provider?: string;
  target_provider?: string;
  model?: string;
  api_key?: string;
}): Promise<AIConfig> => aiRequest("/api/ai/config", payload);

export const testAIProviderApi = (payload: {
  target_provider: string;
  model?: string;
  api_key?: string;
}): Promise<{ success: boolean }> => aiRequest("/api/ai/test", payload);
