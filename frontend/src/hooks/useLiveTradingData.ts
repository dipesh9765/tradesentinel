import { useCallback, useEffect, useRef, useState } from "react";
import {
    fetchHistory,
    fetchKiteBalanceApi,
    fetchOrders,
    fetchPositions,
    fetchQuotes,
    fetchStatus,
    subscribeToLiveTicks,
} from "../services/api";
import { GenConsts, type AuthStateType } from "../constants";
import type { HistoryItem, KiteBalance, OrderRecord, PortfolioSummary, Position, Quote, TradeProposal } from "../types";

interface Options {
    authState: AuthStateType;
    /** Fired when the server pushes a new A+ trade proposal over the websocket. */
    onProposalAlert: (proposal: TradeProposal) => void;
    /** Fired when the server reports an executed order over the websocket. */
    onTradeExecuted: (order: { instrument: string; quantity: number; price: number }) => void;
}

/** Holds the live market/portfolio state, fed by REST snapshots and the websocket tick stream. */
export function useLiveTradingData({ authState, onProposalAlert, onTradeExecuted }: Options) {
    const [quotes, setQuotes] = useState<Quote[]>([]);
    const [selectedSymbol, setSelectedSymbol] = useState("");
    const [positions, setPositions] = useState<Position[]>([]);
    const [orders, setOrders] = useState<OrderRecord[]>([]);
    const [history, setHistory] = useState<HistoryItem[]>([]);
    const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
    const [kiteConnected, setKiteConnected] = useState(false);
    const [kiteBalance, setKiteBalance] = useState<KiteBalance | null>(null);
    const [isLoadingKiteBalance, setIsLoadingKiteBalance] = useState(false);
    const [lastBalanceRefreshTime, setLastBalanceRefreshTime] = useState<string | null>(null);

    // Latest-value refs so long-lived subscriptions never read stale state.
    const selectedSymbolRef = useRef(selectedSymbol);
    const callbacksRef = useRef({ onProposalAlert, onTradeExecuted });
    useEffect(() => {
        selectedSymbolRef.current = selectedSymbol;
    }, [selectedSymbol]);
    useEffect(() => {
        callbacksRef.current = { onProposalAlert, onTradeExecuted };
    }, [onProposalAlert, onTradeExecuted]);

    const loadHistory = useCallback(async () => {
        try {
            setHistory(await fetchHistory());
        } catch (err) {
            console.warn("Failed to load history:", err);
        }
    }, []);

    const refreshBalance = useCallback(async () => {
        setIsLoadingKiteBalance(true);
        try {
            const bal = await fetchKiteBalanceApi();
            setKiteBalance(bal);
            if (bal.connected !== undefined) setKiteConnected(Boolean(bal.connected));
            setLastBalanceRefreshTime(
                new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
            );
        } catch (err) {
            console.warn("Failed to refresh Kite balance:", err);
        } finally {
            setIsLoadingKiteBalance(false);
        }
    }, []);

    const loadInitialData = useCallback(async () => {
        try {
            const [statusData, quotesData, posData, ordersData, historyData] = await Promise.all([
                fetchStatus(),
                fetchQuotes(),
                fetchPositions(),
                fetchOrders(),
                fetchHistory(),
            ]);
            setPortfolio(statusData.portfolio);
            setKiteConnected(Boolean(statusData.kite_active));
            if (statusData.portfolio?.kite_balance) setKiteBalance(statusData.portfolio.kite_balance);
            setQuotes(quotesData);
            if (!selectedSymbolRef.current && quotesData.length > 0) setSelectedSymbol(quotesData[0].symbol);
            setPositions(posData.positions);
            setOrders(ordersData);
            setHistory(historyData);
            void refreshBalance();
        } catch (err) {
            console.warn("Initial data fetch error:", err);
        }
    }, [refreshBalance]);

    /** Re-reads positions, orders, portfolio and history after a trade changes server state. */
    const refreshAfterTrade = useCallback(async () => {
        const [posData, ordersData, statusData] = await Promise.all([fetchPositions(), fetchOrders(), fetchStatus()]);
        setPositions(posData.positions);
        setOrders(ordersData);
        setPortfolio(statusData.portfolio);
        await loadHistory();
    }, [loadHistory]);

    /** Refreshes just the portfolio summary (and optionally the Kite connection flag). */
    const syncStatus = useCallback(async (options: { updateKite?: boolean } = {}) => {
        const statusData = await fetchStatus();
        setPortfolio(statusData.portfolio);
        if (options.updateKite) setKiteConnected(Boolean(statusData.kite_active));
    }, []);

    const reset = useCallback(() => {
        setQuotes([]);
        setPositions([]);
        setOrders([]);
        setKiteBalance(null);
        setLastBalanceRefreshTime(null);
    }, []);

    useEffect(() => {
        if (authState !== GenConsts.AUTH_STATES.AUTHENTICATED) return;

        return subscribeToLiveTicks((data) => {
            if (data.type === GenConsts.WS_EVENTS.TICK || data.type === GenConsts.WS_EVENTS.INIT) {
                if (data.quotes) {
                    setQuotes(data.quotes);
                    if (!selectedSymbolRef.current && data.quotes.length > 0) setSelectedSymbol(data.quotes[0].symbol);
                }
                if (data.portfolio) {
                    setPortfolio(data.portfolio);
                    setKiteConnected(Boolean(data.portfolio.kite_connected));
                    if (data.portfolio.kite_balance) setKiteBalance(data.portfolio.kite_balance);
                }
                if (data.positions) setPositions(data.positions);
            } else if (data.type === GenConsts.WS_EVENTS.TRADE_PROPOSAL_ALERT && data.proposal) {
                callbacksRef.current.onProposalAlert(data.proposal);
            } else if (data.type === "TRADE_EXECUTED_ALERT" && data.execution?.order) {
                callbacksRef.current.onTradeExecuted(data.execution.order);
            }
        });
    }, [authState]);

    return {
        quotes,
        selectedSymbol,
        setSelectedSymbol,
        positions,
        orders,
        history,
        portfolio,
        kiteConnected,
        setKiteConnected,
        kiteBalance,
        isLoadingKiteBalance,
        lastBalanceRefreshTime,
        loadInitialData,
        loadHistory,
        refreshBalance,
        refreshAfterTrade,
        syncStatus,
        reset,
    };
}
