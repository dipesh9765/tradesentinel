import React, { useState, useEffect, useRef } from "react";
import confetti from "canvas-confetti";
import { ShieldAlert, Lock, TrendingUp, List, Layers } from "lucide-react";
import { Header } from "./components/layout";
import { TradeProposalCard, PositionsTable } from "./features/trading";
import { TradingChart, Watchlist } from "./features/market";
import { SettingsModal } from "./features/settings";
import { AuthGatekeeper } from "./features/auth";

import type { Quote, Candle, TradeProposal, Position, OrderRecord, PortfolioSummary, HistoryItem, KiteBalance } from "./types";
import { soundManager } from "./services/sound";
import { notificationManager } from "./services/notifications";
import {
    fetchAuthStatus,
    verifyAuthTokenApi,
    logoutApi,
    setOnUnauthorized,
    fetchStatus,
    fetchQuotes,
    fetchCandles,
    requestAiScan,
    approveTradeApi,
    rejectTradeApi,
    fetchPositions,
    closePositionApi,
    fetchOrders,
    fetchHistory,
    updateSettingsApi,
    fetchKiteLoginUrl,
    generateKiteSessionApi,
    fetchKiteBalanceApi,
    testNotificationApi,
    subscribeToLiveTicks,
    updateTradingModeApi
} from "./services/api";
import { GenConsts, type AuthStateType } from "./constants";

export const App: React.FC = () => {
    // Authentication & Security State
    const [authState, setAuthState] = useState<AuthStateType>(GenConsts.AUTH_STATES.CHECKING);

    const [quotes, setQuotes] = useState<Quote[]>([]);
    const [selectedSymbol, setSelectedSymbol] = useState<string>("");
    const [candles, setCandles] = useState<Candle[]>([]);
    const [isLoadingCandles, setIsLoadingCandles] = useState<boolean>(false);
    const [chartStatus, setChartStatus] = useState<string | null>(null);
    const [chartErrorDetail, setChartErrorDetail] = useState<string | null>(null);
    const [proposal, setProposal] = useState<TradeProposal | null>(null);
    const [positions, setPositions] = useState<Position[]>([]);
    const [orders, setOrders] = useState<OrderRecord[]>([]);
    const [history, setHistory] = useState<HistoryItem[]>([]);
    const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
    const [kiteConnected, setKiteConnected] = useState<boolean>(false);
    const [kiteBalance, setKiteBalance] = useState<KiteBalance | null>(null);
    const [isLoadingKiteBalance, setIsLoadingKiteBalance] = useState<boolean>(false);
    const [lastBalanceRefreshTime, setLastBalanceRefreshTime] = useState<string | null>(null);

    const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>("default");
    const [isScanning, setIsScanning] = useState<boolean>(false);
    const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
    const [mobileTab, setMobileTab] = useState<"chart" | "watchlist" | "positions">("chart");

    const proposalRef = useRef<TradeProposal | null>(proposal);
    const selectedSymbolRef = useRef<string>(selectedSymbol);

    useEffect(() => {
        proposalRef.current = proposal;
    }, [proposal]);

    useEffect(() => {
        selectedSymbolRef.current = selectedSymbol;
    }, [selectedSymbol]);

    // 1. Check Master Password / Authentication State on mount
    useEffect(() => {
        setOnUnauthorized(() => {
            setAuthState(GenConsts.AUTH_STATES.UNAUTHENTICATED);
        });
        checkAuth();
    }, []);

    const checkAuth = async () => {
        try {
            const res = await fetchAuthStatus();
            if (!res.is_initialized) {
                setAuthState(GenConsts.AUTH_STATES.UNINITIALIZED);
            } else if (!res.is_authenticated) {
                setAuthState(GenConsts.AUTH_STATES.UNAUTHENTICATED);
            } else {
                setAuthState(GenConsts.AUTH_STATES.AUTHENTICATED);
                initAuthenticatedSession();
            }
        } catch (e) {
            setAuthState(GenConsts.AUTH_STATES.UNAUTHENTICATED);
        }
    };

    const handleAuthenticated = () => {
        setAuthState(GenConsts.AUTH_STATES.AUTHENTICATED);
        initAuthenticatedSession();
    };

    const handleLogout = async () => {
        await logoutApi();
        setAuthState(GenConsts.AUTH_STATES.UNAUTHENTICATED);
        setQuotes([]);
        setPositions([]);
        setOrders([]);
        setProposal(null);
        setKiteBalance(null);
        setLastBalanceRefreshTime(null);
    };

    // 2. Setup Session Once Verified
    const initAuthenticatedSession = () => {
        loadInitialData();

        // Check for Zerodha Kite OAuth redirect request_token in URL
        const urlParams = new URLSearchParams(window.location.search);
        const reqToken = urlParams.get("request_token");
        if (reqToken) {
            generateKiteSessionApi(reqToken)
                .then(() => {
                    alert("✅ Zerodha Kite Authenticated Successfully for today's live session!");
                    window.history.replaceState({}, document.title, window.location.pathname);
                    loadInitialData();
                })
                .catch((err) => {
                    console.warn("Session generation error:", err);
                });
        }

        if (notificationManager.isSupported()) {
            setNotificationPermission(notificationManager.getPermission());
        }
    };

    // 3. Live WebSocket streaming & Keyboard Shortcuts (Only active when AUTHENTICATED)
    useEffect(() => {
        if (authState !== GenConsts.AUTH_STATES.AUTHENTICATED) return;

        const unsubscribe = subscribeToLiveTicks((data) => {
            if (data.type === GenConsts.WS_EVENTS.TICK || data.type === GenConsts.WS_EVENTS.INIT) {
                if (data.quotes) {
                    setQuotes(data.quotes);
                    if (!selectedSymbolRef.current && data.quotes.length > 0) {
                        setSelectedSymbol(data.quotes[0].symbol);
                    }
                }
                if (data.portfolio) {
                    setPortfolio(data.portfolio);
                    setKiteConnected(Boolean(data.portfolio.kite_connected));
                    if (data.portfolio.kite_balance) {
                        setKiteBalance(data.portfolio.kite_balance);
                    }
                }
                if (data.positions) setPositions(data.positions);
            } else if (data.type === GenConsts.WS_EVENTS.TRADE_PROPOSAL_ALERT && data.proposal) {
                setProposal(data.proposal);
                soundManager.playAlert();
                notificationManager.notifyTradeProposal(data.proposal);
            } else if (data.type === "TRADE_EXECUTED_ALERT" && data.execution) {
                const ord = data.execution.order;
                if (ord) {
                    notificationManager.notifyTradeExecuted(ord.instrument, ord.quantity, ord.price);
                }
            }
        });

        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
                return;
            }

            const activeProposal = proposalRef.current;
            if (activeProposal && activeProposal.status === GenConsts.STATUSES.PENDING_APPROVAL) {
                if (e.key === "a" || e.key === "A" || e.key === "Enter") {
                    e.preventDefault();
                    handleApproveProposal(activeProposal.proposal_id);
                } else if (e.key === "r" || e.key === "R" || e.key === "Escape") {
                    e.preventDefault();
                    handleRejectProposal(activeProposal.proposal_id);
                }
            } else {
                if (e.key === "s" || e.key === "S") {
                    e.preventDefault();
                    handleTriggerScan(selectedSymbolRef.current);
                }
            }
        };

        window.addEventListener("keydown", handleKeyDown);

        return () => {
            unsubscribe();
            window.removeEventListener("keydown", handleKeyDown);
        };
    }, [authState]);

    // 4. Continuous 30-Second Token & Kite Authentication Verification Heartbeat
    useEffect(() => {
        if (authState !== GenConsts.AUTH_STATES.AUTHENTICATED) return;

        const heartbeatInterval = setInterval(async () => {
            try {
                const res = await verifyAuthTokenApi();
                if (res.kite_token_check && res.kite_token_check.valid !== undefined) {
                    setKiteConnected(Boolean(res.kite_token_check.valid));
                }
            } catch (err) {
                console.warn("30s token verification failed:", err);
                setAuthState(GenConsts.AUTH_STATES.UNAUTHENTICATED);
            }
        }, GenConsts.INTERVALS.KITE_VERIFY_MS);

        return () => clearInterval(heartbeatInterval);
    }, [authState]);

    // 5. Fetch candles when selected symbol changes
    useEffect(() => {
        if (authState !== GenConsts.AUTH_STATES.AUTHENTICATED || !selectedSymbol) return;
        loadCandles(selectedSymbol, true);
        const interval = setInterval(() => {
            loadCandles(selectedSymbol, false);
        }, GenConsts.INTERVALS.CANDLE_POLL_MS);
        return () => clearInterval(interval);
    }, [selectedSymbol, authState]);

    const loadHistory = async () => {
        try {
            const h = await fetchHistory();
            setHistory(h);
        } catch (e) {
            console.warn("Failed to load history:", e);
        }
    };

    const handleRefreshBalance = async () => {
        setIsLoadingKiteBalance(true);
        try {
            const bal = await fetchKiteBalanceApi();
            setKiteBalance(bal);
            if (bal.connected !== undefined) {
                setKiteConnected(Boolean(bal.connected));
            }
            const now = new Date();
            const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
            setLastBalanceRefreshTime(timeStr);
        } catch (err) {
            console.warn("Failed to refresh Kite balance:", err);
        } finally {
            setIsLoadingKiteBalance(false);
        }
    };

    const loadInitialData = async () => {
        try {
            const [statusData, quotesData, posData, ordersData, historyData] = await Promise.all([
                fetchStatus(),
                fetchQuotes(),
                fetchPositions(),
                fetchOrders(),
                fetchHistory()
            ]);
            setPortfolio(statusData.portfolio);
            setKiteConnected(Boolean(statusData.kite_active));
            if (statusData.portfolio?.kite_balance) {
                setKiteBalance(statusData.portfolio.kite_balance);
            }
            setQuotes(quotesData);
            if (!selectedSymbolRef.current && quotesData.length > 0) {
                setSelectedSymbol(quotesData[0].symbol);
            }
            setPositions(posData.positions);
            setOrders(ordersData);
            setHistory(historyData);
            handleRefreshBalance();
        } catch (err) {
            console.warn("Initial data fetch error:", err);
        }
    };

    const loadCandles = async (symbol: string, showLoading: boolean = false) => {
        if (!symbol) {
            setCandles([]);
            setChartStatus(GenConsts.CHART_STATUSES.NO_DATA);
            return;
        }
        if (showLoading) setIsLoadingCandles(true);
        try {
            const res = await fetchCandles(symbol);
            setCandles(res.candles || []);
            setChartStatus(res.status || (res.candles && res.candles.length > 0 ? GenConsts.CHART_STATUSES.OK : GenConsts.CHART_STATUSES.NO_DATA));
            setChartErrorDetail(res.error_detail || res.message || null);
        } catch (e: any) {
            console.warn("Failed to load candles:", e);
            setCandles([]);
            setChartStatus(GenConsts.CHART_STATUSES.KITE_BROKER_ERROR);
            setChartErrorDetail(e?.message || "Failed to reach market data service.");
        } finally {
            if (showLoading) setIsLoadingCandles(false);
        }
    };

    const handleTriggerScan = async (symbol: string) => {
        if (!kiteConnected) {
            alert("Zerodha Kite Connect is not configured or authenticated. Please add credentials in Settings to scan live market setups.");
            setIsSettingsOpen(true);
            return;
        }

        setIsScanning(true);
        soundManager.playClick();
        try {
            const newProposal = await requestAiScan(symbol);
            setProposal(newProposal);
            await loadHistory();
            soundManager.playAlert();
            notificationManager.notifyTradeProposal(newProposal);
        } catch (err: any) {
            alert("Scan failed: " + err.message);
        } finally {
            setIsScanning(false);
        }
    };

    const handleApproveProposal = async (proposalId: string) => {
        try {
            soundManager.playSuccess();
            await approveTradeApi(proposalId);
            setProposal(null);

            const [posData, ordersData, statusData] = await Promise.all([
                fetchPositions(),
                fetchOrders(),
                fetchStatus()
            ]);
            setPositions(posData.positions);
            setOrders(ordersData);
            setPortfolio(statusData.portfolio);
            await loadHistory();

            confetti({ particleCount: 50, spread: 60, origin: { y: 0.6 } });
        } catch (err: any) {
            alert("Trade execution error: " + err.message);
        }
    };

    const handleRejectProposal = async (proposalId: string) => {
        try {
            soundManager.playClick();
            await rejectTradeApi(proposalId);
            setProposal(null);
            await loadHistory();
        } catch (err: any) {
            alert("Rejection error: " + err.message);
        }
    };

    const handleClosePosition = async (positionId: string) => {
        try {
            soundManager.playClick();
            await closePositionApi(positionId);
            const [posData, ordersData, statusData] = await Promise.all([
                fetchPositions(),
                fetchOrders(),
                fetchStatus()
            ]);
            setPositions(posData.positions);
            setOrders(ordersData);
            setPortfolio(statusData.portfolio);
            await loadHistory();
        } catch (err: any) {
            alert("Failed to close position: " + err.message);
        }
    };

    const handleRequestNotificationPermission = async () => {
        const granted = await notificationManager.requestPermission();
        setNotificationPermission(notificationManager.getPermission());
        if (granted) {
            notificationManager.sendNotification("🚀 TradeSentinel Alerts Active", {
                body: "Windows notifications will now pop up whenever an A+ setup is spotted!"
            });
        }
    };

    const handleSaveSettings = async (newSettings: any) => {
        await updateSettingsApi(newSettings);
        const statusData = await fetchStatus();
        setPortfolio(statusData.portfolio);
        setKiteConnected(Boolean(statusData.kite_active));
        await loadInitialData();
        await handleRefreshBalance();
    };

    const handleToggleMode = async (newMode: "PAPER" | "LIVE") => {
        try {
            await updateTradingModeApi(newMode);
            const statusData = await fetchStatus();
            setPortfolio(statusData.portfolio);
        } catch (err: any) {
            alert("Failed to switch trading mode: " + (err.message || err));
        }
    };

    const handleTestNotification = async () => {
        notificationManager.sendNotification("🎯 TradeSentinel: Opportunity Alert", {
            body: "Sample: NIFTY 24850 CE Buy @ 120, SL: 108, Target: 156. Notifications working properly!"
        });
        await testNotificationApi();
    };

    const handleOpenKiteLogin = async () => {
        try {
            const loginUrl = await fetchKiteLoginUrl();
            window.open(loginUrl, "_blank");
        } catch (e: any) {
            alert(e.message || "Could not fetch Kite login URL. Please make sure Kite API Key is entered in Settings.");
        }
    };

    // ==================== SECURITY GATEKEEPER LOCK ====================
    if (authState === GenConsts.AUTH_STATES.CHECKING) {
        return (
            <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#060911", color: "#00f0ff" }}>
                <div style={{ textAlign: "center" }}>
                    <Lock size={36} style={{ animation: "pulse 1.5s infinite", margin: "0 auto 16px" }} />
                    <div style={{ fontSize: "16px", fontWeight: 700, letterSpacing: "0.5px" }}>Verifying TradeSentinel Security Vault...</div>
                </div>
            </div>
        );
    }

    if (authState === GenConsts.AUTH_STATES.UNINITIALIZED || authState === GenConsts.AUTH_STATES.UNAUTHENTICATED) {
        return (
            <AuthGatekeeper
                isInitialized={authState === GenConsts.AUTH_STATES.UNAUTHENTICATED}
                onAuthenticated={handleAuthenticated}
            />
        );
    }

    // ==================== AUTHENTICATED APPLICATION ====================
    return (
        <div className="app-container">
            {/* Top Header */}
            <Header
                portfolio={portfolio}
                kiteBalance={kiteBalance}
                isLoadingBalance={isLoadingKiteBalance}
                onRefreshBalance={handleRefreshBalance}
                lastBalanceRefreshTime={lastBalanceRefreshTime}
                onOpenSettings={() => setIsSettingsOpen(true)}
                onToggleMode={handleToggleMode}
                notificationPermission={notificationPermission}
                onRequestNotificationPermission={handleRequestNotificationPermission}
                kiteConnected={kiteConnected}
                onLogout={handleLogout}
            />

            {/* Kite Configuration Alert Banner if Not Connected */}
            {!kiteConnected && (
                <div
                    style={{
                        background: "rgba(255, 179, 0, 0.12)",
                        border: "1px solid rgba(255, 179, 0, 0.4)",
                        borderRadius: "14px",
                        padding: "14px 18px",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        marginBottom: "16px",
                        flexWrap: "wrap",
                        gap: "12px"
                    }}
                >
                    <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                        <div style={{ background: "rgba(255, 179, 0, 0.2)", padding: "8px", borderRadius: "8px", display: "flex" }}>
                            <ShieldAlert size={22} color="#ffb300" />
                        </div>
                        <div>
                            <div style={{ fontWeight: 800, color: "#ffb300", fontSize: "14px", letterSpacing: "0.2px" }}>
                                Zerodha Kite Connect Setup Required (Real Data Mode)
                            </div>
                            <div style={{ color: "#cbd5e1", fontSize: "12px", marginTop: "2px" }}>
                                Authenticate today's Kite session in Settings to stream authentic NSE/NFO market quotes and live charts.
                            </div>
                        </div>
                    </div>
                    <button
                        onClick={() => setIsSettingsOpen(true)}
                        className="btn btn-primary"
                        style={{
                            padding: "8px 16px",
                            fontSize: "12.5px",
                            fontWeight: 700,
                            background: "#ffb300",
                            color: "#0c111d",
                            borderColor: "#ffb300"
                        }}
                    >
                        Configure Kite Credentials
                    </button>
                </div>
            )}

            {/* Mobile View Selector Tabs (Phones only) */}
            <div className="mobile-tabs-container">
                <button
                    onClick={() => setMobileTab("chart")}
                    className={`mobile-tab-btn ${mobileTab === "chart" ? "active" : ""}`}
                >
                    <TrendingUp size={15} />
                    <span>Chart & AI</span>
                </button>
                <button
                    onClick={() => setMobileTab("watchlist")}
                    className={`mobile-tab-btn ${mobileTab === "watchlist" ? "active" : ""}`}
                >
                    <List size={15} />
                    <span>Watchlist ({quotes.length})</span>
                </button>
                <button
                    onClick={() => setMobileTab("positions")}
                    className={`mobile-tab-btn ${mobileTab === "positions" ? "active" : ""}`}
                >
                    <Layers size={15} />
                    <span>Positions ({positions.length})</span>
                </button>
            </div>

            {/* Main Trading Area Layout */}
            <div className="trading-layout">
                {/* Left Column: Watchlist */}
                <div style={{ display: typeof window !== "undefined" && window.innerWidth <= 900 && mobileTab !== "watchlist" ? undefined : "block" }} className={mobileTab === "watchlist" ? "mobile-only" : "desktop-only"}>
                    <Watchlist
                        quotes={quotes}
                        selectedSymbol={selectedSymbol}
                        onSelectSymbol={(sym) => {
                            setSelectedSymbol(sym);
                            setMobileTab("chart");
                        }}
                    />
                </div>

                {/* Center Column: Interactive TradingView-Style Chart */}
                <div className="chart-column" style={{ display: typeof window !== "undefined" && window.innerWidth <= 900 && mobileTab !== "chart" ? undefined : "block" }}>
                    <TradingChart
                        symbol={selectedSymbol || (quotes[0]?.symbol || "NIFTY 50")}
                        candles={candles}
                        livePrice={quotes.find((q) => q.symbol === selectedSymbol)?.ltp}
                        onTriggerScan={() => handleTriggerScan(selectedSymbol)}
                        isScanning={isScanning}
                        isLoadingCandles={isLoadingCandles}
                        status={chartStatus}
                        errorDetail={chartErrorDetail}
                        onOpenSettings={() => setIsSettingsOpen(true)}
                    />
                </div>

                {/* Right Column: AI Trade Proposal & Portfolio Summary */}
                <div className="control-column">
                    <TradeProposalCard
                        proposal={proposal}
                        onApprove={handleApproveProposal}
                        onReject={handleRejectProposal}
                        onTriggerManualScan={() => handleTriggerScan(selectedSymbol)}
                        isScanning={isScanning}
                    />
                </div>
            </div>

            {/* Bottom Section: Active Positions & Historical Audit Log */}
            <div style={{ marginTop: "24px", display: typeof window !== "undefined" && window.innerWidth <= 900 && mobileTab !== "positions" ? undefined : "block" }} className={mobileTab === "positions" ? "mobile-only" : ""}>
                <PositionsTable
                    positions={positions}
                    orders={orders}
                    history={history}
                    onClosePosition={handleClosePosition}
                />
            </div>

            {/* Encrypted Vault & Webhook Settings Modal */}
            <SettingsModal
                isOpen={isSettingsOpen}
                onClose={() => setIsSettingsOpen(false)}
                onSave={handleSaveSettings}
                onOpenKiteLogin={handleOpenKiteLogin}
                onTestNotification={handleTestNotification}
            />
        </div>
    );
};

export default App;
