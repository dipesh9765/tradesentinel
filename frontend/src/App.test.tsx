import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("./services/api", () => ({
    fetchAuthStatus: vi.fn(),
    setOnUnauthorized: vi.fn(),
    logoutApi: vi.fn(),
    verifyAuthTokenApi: vi.fn(),
    updateSettingsApi: vi.fn(),
    fetchKiteLoginUrl: vi.fn(),
    generateKiteSessionApi: vi.fn(),
    testNotificationApi: vi.fn(),
    updateTradingModeApi: vi.fn(),
    setupMasterPasswordApi: vi.fn(),
    loginMasterPasswordApi: vi.fn(),
    setAuthToken: vi.fn(),
    getAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    subscribeToLiveTicks: vi.fn(() => () => {}),
    fetchStatus: vi.fn(),
    fetchQuotes: vi.fn(),
    fetchPositions: vi.fn(),
    fetchOrders: vi.fn(),
    fetchHistory: vi.fn(),
    fetchCandles: vi.fn(),
    fetchKiteBalanceApi: vi.fn(),
    requestAiScan: vi.fn(),
    approveTradeApi: vi.fn(),
    rejectTradeApi: vi.fn(),
    closePositionApi: vi.fn(),
}));

import { fetchAuthStatus } from "./services/api";
import App from "./App";

describe("App security gate", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("shows the vault check first", () => {
        vi.mocked(fetchAuthStatus).mockReturnValue(new Promise(() => {}));
        render(<App />);
        expect(screen.getByText(/verifying tradesentinel security vault/i)).toBeInTheDocument();
    });

    it("shows the gatekeeper instead of the terminal when the vault is locked", async () => {
        vi.mocked(fetchAuthStatus).mockResolvedValue({ is_initialized: true, is_authenticated: false, is_vault_unlocked: false });
        render(<App />);
        await waitFor(() => expect(screen.queryByText(/verifying tradesentinel security vault/i)).not.toBeInTheDocument());
        expect(screen.queryByText(/Zerodha Kite Connect Setup Required/i)).not.toBeInTheDocument();
        expect(document.querySelector("input[type='password']")).not.toBeNull();
    });
});
