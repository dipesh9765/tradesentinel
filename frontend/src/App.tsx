import React, { useCallback, useEffect, useRef, useState } from "react";
import { Lock, TrendingUp, List, Layers } from "lucide-react";
import { Header } from "./components/layout";
import { KiteSetupBanner } from "./components/layout/KiteSetupBanner";
import { TradeProposalCard, PositionsTable } from "./features/trading";
import { TradingChart, Watchlist } from "./features/market";
import { SettingsModal } from "./features/settings";
import { AuthGatekeeper } from "./features/auth";

import type { TradeProposal } from "./types";
import { notificationManager } from "./services/notifications";
import { showAlert } from "./services/dialogs";
import {
    updateSettingsApi,
    fetchKiteLoginUrl,
    generateKiteSessionApi,
    testNotificationApi,
    updateTradingModeApi,
} from "./services/api";
import { GenConsts } from "./constants";
import { errorMessage } from "./utils/errors";
import { useAuthSession } from "./hooks/useAuthSession";
import { useCandles } from "./hooks/useCandles";
import { useLiveTradingData } from "./hooks/useLiveTradingData";
import { useTokenHeartbeat } from "./hooks/useTokenHeartbeat";
import { useTradeActions } from "./hooks/useTradeActions";

type UpdateSettingsPayload = Parameters<typeof updateSettingsApi>[0];

const isNarrowViewport = () => typeof window !== "undefined" && window.innerWidth <= 900;

export const App: React.FC = () => {
    const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>("default");
    const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
    const [mobileTab, setMobileTab] = useState<"chart" | "watchlist" | "positions">("chart");

    // The session bootstrap needs data hooks created after the auth hook, so it is reached through a ref.
    const initSessionRef = useRef<() => void>(() => {});
    const { authState, markAuthenticated, markUnauthenticated, logout } = useAuthSession({
        onAuthenticated: () => initSessionRef.current(),
    });

    // The live feed pushes server alerts into the trade-actions hook through these stable callbacks.
    const receiveProposalRef = useRef<(proposal: TradeProposal) => void>(() => {});
    const onProposalAlert = useCallback((proposal: TradeProposal) => receiveProposalRef.current(proposal), []);
    const onTradeExecuted = useCallback(
        (order: { instrument: string; quantity: number; price: number }) =>
            notificationManager.notifyTradeExecuted(order.instrument, order.quantity, order.price),
        [],
    );

    const data = useLiveTradingData({ authState, onProposalAlert, onTradeExecuted });
    const {
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
    } = data;

    const openSettings = useCallback(() => setIsSettingsOpen(true), []);
    const { proposal, isScanning, triggerScan, approve, reject, closePosition, receiveProposal, clearProposal } =
        useTradeActions({
            authState,
            selectedSymbol,
            kiteConnected,
            onNeedsKiteSetup: openSettings,
            refreshAfterTrade,
            loadHistory,
        });
    useEffect(() => {
        receiveProposalRef.current = receiveProposal;
    }, [receiveProposal]);

    const {
        candles,
        isLoading: isLoadingCandles,
        status: chartStatus,
        errorDetail: chartErrorDetail,
    } = useCandles(selectedSymbol, authState === GenConsts.AUTH_STATES.AUTHENTICATED);

    useTokenHeartbeat({ authState, onKiteStatus: setKiteConnected, onSessionLost: markUnauthenticated });

    // Session bootstrap: initial data, Zerodha OAuth redirect token, notification permission.
    useEffect(() => {
        initSessionRef.current = () => {
        void loadInitialData();

        const reqToken = new URLSearchParams(window.location.search).get("request_token");
        if (reqToken) {
            generateKiteSessionApi(reqToken)
                .then(() => {
                    showAlert("Zerodha Kite authenticated successfully for today's live session.");
                    window.history.replaceState({}, document.title, window.location.pathname);
                    void loadInitialData();
                })
                .catch((err) => console.warn("Session generation error:", err));
        }

        if (notificationManager.isSupported()) {
            setNotificationPermission(notificationManager.getPermission());
        }
    };
    });

    const handleLogout = async () => {
        await logout();
        data.reset();
        clearProposal();
    };

    const handleRequestNotificationPermission = async () => {
        const granted = await notificationManager.requestPermission();
        setNotificationPermission(notificationManager.getPermission());
        if (granted) {
            notificationManager.sendNotification("TradeSentinel Alerts Active", {
                body: "Browser notifications will now pop up whenever an A+ setup is spotted!",
            });
        }
    };

    const handleSaveSettings = async (newSettings: UpdateSettingsPayload) => {
        await updateSettingsApi(newSettings);
        await syncStatus({ updateKite: true });
        await loadInitialData();
        await refreshBalance();
    };

    const handleToggleMode = async (newMode: "PAPER" | "LIVE") => {
        try {
            await updateTradingModeApi(newMode);
            await syncStatus();
        } catch (err) {
            showAlert("Failed to switch trading mode: " + errorMessage(err));
        }
    };

    const handleTestNotification = async () => {
        notificationManager.sendNotification("TradeSentinel: Opportunity Alert", {
            body: "Sample: NIFTY 24850 CE Buy @ 120, SL: 108, Target: 156. Notifications working properly!",
        });
        await testNotificationApi();
    };

    const handleOpenKiteLogin = async () => {
        try {
            window.open(await fetchKiteLoginUrl(), "_blank");
        } catch (err) {
            showAlert(
                errorMessage(err, "Could not fetch Kite login URL. Please make sure Kite API Key is entered in Settings."),
            );
        }
    };

    if (authState === GenConsts.AUTH_STATES.CHECKING) {
        return (
            <div
                style={{
                    minHeight: "100vh",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: "#060911",
                    color: "#00f0ff",
                }}
            >
                <div style={{ textAlign: "center" }}>
                    <Lock size={36} style={{ animation: "pulse 1.5s infinite", margin: "0 auto 16px" }} />
                    <div style={{ fontSize: "16px", fontWeight: 700, letterSpacing: "0.5px" }}>
                        Verifying TradeSentinel Security Vault...
                    </div>
                </div>
            </div>
        );
    }

    if (authState === GenConsts.AUTH_STATES.UNINITIALIZED || authState === GenConsts.AUTH_STATES.UNAUTHENTICATED) {
        return (
            <AuthGatekeeper
                isInitialized={authState === GenConsts.AUTH_STATES.UNAUTHENTICATED}
                onAuthenticated={markAuthenticated}
            />
        );
    }

    return (
        <div className="app-container">
            <Header
                portfolio={portfolio}
                kiteBalance={kiteBalance}
                isLoadingBalance={isLoadingKiteBalance}
                onRefreshBalance={refreshBalance}
                lastBalanceRefreshTime={lastBalanceRefreshTime}
                onOpenSettings={openSettings}
                onToggleMode={handleToggleMode}
                notificationPermission={notificationPermission}
                onRequestNotificationPermission={handleRequestNotificationPermission}
                kiteConnected={kiteConnected}
                onLogout={handleLogout}
            />

            {!kiteConnected && <KiteSetupBanner onConfigure={openSettings} />}

            {/* Mobile view selector tabs (phones only) */}
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

            <div className="trading-layout">
                <div
                    style={{ display: isNarrowViewport() && mobileTab !== "watchlist" ? undefined : "block" }}
                    className={mobileTab === "watchlist" ? "mobile-only" : "desktop-only"}
                >
                    <Watchlist
                        quotes={quotes}
                        selectedSymbol={selectedSymbol}
                        onSelectSymbol={(sym) => {
                            setSelectedSymbol(sym);
                            setMobileTab("chart");
                        }}
                    />
                </div>

                <div
                    className="chart-column"
                    style={{ display: isNarrowViewport() && mobileTab !== "chart" ? undefined : "block" }}
                >
                    <TradingChart
                        symbol={selectedSymbol || quotes[0]?.symbol || "NIFTY 50"}
                        candles={candles}
                        livePrice={quotes.find((q) => q.symbol === selectedSymbol)?.ltp}
                        onTriggerScan={() => triggerScan(selectedSymbol)}
                        isScanning={isScanning}
                        isLoadingCandles={isLoadingCandles}
                        status={chartStatus}
                        errorDetail={chartErrorDetail}
                        onOpenSettings={openSettings}
                    />
                </div>

                <div className="control-column">
                    <TradeProposalCard
                        proposal={proposal}
                        onApprove={approve}
                        onReject={reject}
                        onTriggerManualScan={() => triggerScan(selectedSymbol)}
                        isScanning={isScanning}
                    />
                </div>
            </div>

            <div
                style={{ marginTop: "24px", display: isNarrowViewport() && mobileTab !== "positions" ? undefined : "block" }}
                className={mobileTab === "positions" ? "mobile-only" : ""}
            >
                <PositionsTable positions={positions} orders={orders} history={history} onClosePosition={closePosition} />
            </div>

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
