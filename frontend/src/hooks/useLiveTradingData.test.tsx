import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { GenConsts } from "../constants";
import type { PortfolioSummary, Quote, TradeProposal } from "../types";

vi.mock("../services/api", () => ({
    fetchHistory: vi.fn(),
    fetchKiteBalanceApi: vi.fn(),
    fetchOrders: vi.fn(),
    fetchPositions: vi.fn(),
    fetchQuotes: vi.fn(),
    fetchStatus: vi.fn(),
    subscribeToLiveTicks: vi.fn(),
}));

import {
    fetchHistory,
    fetchKiteBalanceApi,
    fetchOrders,
    fetchPositions,
    fetchQuotes,
    fetchStatus,
    subscribeToLiveTicks,
} from "../services/api";
import { useLiveTradingData } from "./useLiveTradingData";

type TickHandler = Parameters<typeof subscribeToLiveTicks>[0];

const QUOTES = [{ symbol: "NIFTY 50", ltp: 24800 }, { symbol: "BANK NIFTY", ltp: 52000 }] as Quote[];
const PORTFOLIO = { mode: "PAPER", kite_connected: false } as unknown as PortfolioSummary;

function primeRest() {
    vi.mocked(fetchStatus).mockResolvedValue({ portfolio: PORTFOLIO, kite_active: true } as Awaited<ReturnType<typeof fetchStatus>>);
    vi.mocked(fetchQuotes).mockResolvedValue(QUOTES);
    vi.mocked(fetchPositions).mockResolvedValue({ positions: [], summary: PORTFOLIO });
    vi.mocked(fetchOrders).mockResolvedValue([]);
    vi.mocked(fetchHistory).mockResolvedValue([]);
    vi.mocked(fetchKiteBalanceApi).mockResolvedValue({ connected: true } as Awaited<ReturnType<typeof fetchKiteBalanceApi>>);
}

function setup(authState: Parameters<typeof useLiveTradingData>[0]["authState"] = GenConsts.AUTH_STATES.AUTHENTICATED) {
    const onProposalAlert = vi.fn();
    const onTradeExecuted = vi.fn();
    let emit: TickHandler = () => {};
    const unsubscribe = vi.fn();
    vi.mocked(subscribeToLiveTicks).mockImplementation((handler) => {
        emit = handler;
        return unsubscribe;
    });
    const hook = renderHook(() => useLiveTradingData({ authState, onProposalAlert, onTradeExecuted }));
    return { ...hook, onProposalAlert, onTradeExecuted, unsubscribe, emit: (d: unknown) => act(() => emit(d as never)) };
}

describe("useLiveTradingData", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        primeRest();
    });

    it("does not subscribe to the stream while logged out", () => {
        setup(GenConsts.AUTH_STATES.UNAUTHENTICATED);
        expect(subscribeToLiveTicks).not.toHaveBeenCalled();
    });

    it("loads the initial snapshot and selects the first symbol", async () => {
        const { result } = setup();
        await act(() => result.current.loadInitialData());
        expect(result.current.quotes).toEqual(QUOTES);
        expect(result.current.selectedSymbol).toBe("NIFTY 50");
        expect(result.current.kiteConnected).toBe(true);
        expect(result.current.portfolio).toEqual(PORTFOLIO);
        await waitFor(() => expect(result.current.lastBalanceRefreshTime).not.toBeNull());
    });

    it("keeps an already selected symbol when data reloads", async () => {
        const { result } = setup();
        await act(() => result.current.loadInitialData());
        act(() => result.current.setSelectedSymbol("BANK NIFTY"));
        await act(() => result.current.loadInitialData());
        expect(result.current.selectedSymbol).toBe("BANK NIFTY");
    });

    it("tolerates a failed snapshot without throwing", async () => {
        vi.mocked(fetchStatus).mockRejectedValue(new Error("down"));
        const { result } = setup();
        await act(() => result.current.loadInitialData());
        expect(result.current.quotes).toEqual([]);
    });

    it("applies websocket ticks to quotes, portfolio and connection flag", async () => {
        const { result, emit } = setup();
        emit({ type: GenConsts.WS_EVENTS.TICK, quotes: QUOTES, portfolio: { ...PORTFOLIO, kite_connected: true }, positions: [] });
        expect(result.current.quotes).toEqual(QUOTES);
        expect(result.current.kiteConnected).toBe(true);
        expect(result.current.selectedSymbol).toBe("NIFTY 50");
    });

    it("forwards proposal and execution alerts to the callbacks", () => {
        const { emit, onProposalAlert, onTradeExecuted } = setup();
        const proposal = { proposal_id: "p-1" } as TradeProposal;
        emit({ type: GenConsts.WS_EVENTS.TRADE_PROPOSAL_ALERT, proposal });
        expect(onProposalAlert).toHaveBeenCalledWith(proposal);

        const order = { instrument: "NIFTY 24850 CE", quantity: 75, price: 120 };
        emit({ type: "TRADE_EXECUTED_ALERT", execution: { order } });
        expect(onTradeExecuted).toHaveBeenCalledWith(order);
    });

    it("unsubscribes on unmount", () => {
        const { unmount, unsubscribe } = setup();
        unmount();
        expect(unsubscribe).toHaveBeenCalled();
    });

    it("refreshAfterTrade re-reads positions, orders, portfolio and history", async () => {
        const { result } = setup();
        await act(() => result.current.refreshAfterTrade());
        expect(fetchPositions).toHaveBeenCalled();
        expect(fetchOrders).toHaveBeenCalled();
        expect(fetchStatus).toHaveBeenCalled();
        expect(fetchHistory).toHaveBeenCalled();
    });

    it("syncStatus only touches the connection flag when asked", async () => {
        const { result } = setup();
        await act(() => result.current.syncStatus());
        expect(result.current.kiteConnected).toBe(false);
        await act(() => result.current.syncStatus({ updateKite: true }));
        expect(result.current.kiteConnected).toBe(true);
    });

    it("reset clears per-session data", async () => {
        const { result } = setup();
        await act(() => result.current.loadInitialData());
        act(() => result.current.reset());
        expect(result.current.quotes).toEqual([]);
        expect(result.current.kiteBalance).toBeNull();
    });
});
