import React, { useRef, useEffect } from "react";
import { ShieldAlert, AlertTriangle, RefreshCw, Settings, BarChart2 } from "lucide-react";
import type { Candle, TradeProposal } from "../types";

interface TradingChartProps {
    symbol: string;
    candles: Candle[];
    livePrice?: number;
    proposal?: TradeProposal | null;
    isLoading?: boolean;
    isLoadingCandles?: boolean;
    chartStatus?: string | null;
    status?: string | null;
    errorMessage?: string | null;
    errorDetail?: string | null;
    kiteConnected?: boolean;
    isScanning?: boolean;
    onTriggerScan?: () => Promise<void> | void;
    onOpenSettings?: () => void;
    onRetry?: () => void;
}

export const TradingChart: React.FC<TradingChartProps> = ({
    symbol,
    candles,
    livePrice: _livePrice,
    proposal,
    isLoading = false,
    isLoadingCandles = false,
    chartStatus = null,
    status = null,
    errorMessage = null,
    errorDetail = null,
    kiteConnected = false,
    isScanning: _isScanning,
    onTriggerScan: _onTriggerScan,
    onOpenSettings,
    onRetry
}) => {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const effectiveLoading = isLoading || isLoadingCandles;
    const effectiveStatus = chartStatus || status;
    const effectiveError = errorMessage || errorDetail;

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas || candles.length === 0) return;

        const draw = () => {
            const ctx = canvas.getContext("2d");
            if (!ctx) return;

            // Handle high DPI & Responsive width
            const dpr = window.devicePixelRatio || 1;
            const rect = canvas.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return;

            canvas.width = rect.width * dpr;
            canvas.height = rect.height * dpr;
            ctx.scale(dpr, dpr);

            const width = rect.width;
            const height = rect.height;
            const padding = { top: 30, right: 65, bottom: 30, left: 10 };
            const chartWidth = width - padding.left - padding.right;
            const chartHeight = height - padding.top - padding.bottom;

            // Clear
            ctx.clearRect(0, 0, width, height);

            // Calculate Price Extents
            let minPrice = Math.min(...candles.map((c) => c.low));
            let maxPrice = Math.max(...candles.map((c) => c.high));

            // Include proposal levels if active
            if (proposal) {
                minPrice = Math.min(minPrice, proposal.stop_loss, proposal.entry_price);
                maxPrice = Math.max(maxPrice, proposal.target ?? (proposal as any).target_1 ?? proposal.entry_price, proposal.entry_price);
            }

            const priceRange = maxPrice - minPrice || 1;
            const candleWidth = Math.max(2, (chartWidth / candles.length) - 3);

            const getY = (price: number) => {
                return padding.top + chartHeight - ((price - minPrice) / priceRange) * chartHeight;
            };

            // Draw Grid Lines (4 horizontal levels)
            ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
            ctx.lineWidth = 1;
            ctx.fillStyle = "rgba(255, 255, 255, 0.4)";
            ctx.font = "10px Inter, sans-serif";
            ctx.textAlign = "left";

            for (let i = 0; i <= 4; i++) {
                const priceLevel = minPrice + (priceRange * i) / 4;
                const y = getY(priceLevel);
                ctx.beginPath();
                ctx.moveTo(padding.left, y);
                ctx.lineTo(width - padding.right, y);
                ctx.stroke();

                ctx.fillText(`₹${priceLevel.toFixed(1)}`, width - padding.right + 8, y + 3);
            }

            // Draw Candles
            candles.forEach((c, idx) => {
                const x = padding.left + idx * (candleWidth + 3);
                const isBull = c.close >= c.open;
                ctx.fillStyle = isBull ? "#00f0ff" : "#ff0055";
                ctx.strokeStyle = isBull ? "#00f0ff" : "#ff0055";

                // Wick
                ctx.beginPath();
                ctx.moveTo(x + candleWidth / 2, getY(c.high));
                ctx.lineTo(x + candleWidth / 2, getY(c.low));
                ctx.stroke();

                // Body
                const yOpen = getY(c.open);
                const yClose = getY(c.close);
                const bodyHeight = Math.max(2, Math.abs(yOpen - yClose));
                ctx.fillRect(x, Math.min(yOpen, yClose), candleWidth, bodyHeight);
            });

            // Draw EMA 9 (Cyan line)
            ctx.strokeStyle = "#00f0ff";
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            let startedEma9 = false;
            candles.forEach((c, idx) => {
                const val = c.ema_9 ?? c.ema9;
                if (val != null) {
                    const x = padding.left + idx * (candleWidth + 3) + candleWidth / 2;
                    const y = getY(val);
                    if (!startedEma9) {
                        ctx.moveTo(x, y);
                        startedEma9 = true;
                    } else {
                        ctx.lineTo(x, y);
                    }
                }
            });
            ctx.stroke();

            // Draw EMA 21 (Yellow line)
            ctx.strokeStyle = "#ffb703";
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            let startedEma21 = false;
            candles.forEach((c, idx) => {
                const val = c.ema_21 ?? c.ema21;
                if (val != null) {
                    const x = padding.left + idx * (candleWidth + 3) + candleWidth / 2;
                    const y = getY(val);
                    if (!startedEma21) {
                        ctx.moveTo(x, y);
                        startedEma21 = true;
                    } else {
                        ctx.lineTo(x, y);
                    }
                }
            });
            ctx.stroke();

            // Draw VWAP (Purple dashed line)
            ctx.strokeStyle = "#c084fc";
            ctx.lineWidth = 1.5;
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            let startedVwap = false;
            candles.forEach((c, idx) => {
                if (c.vwap != null) {
                    const x = padding.left + idx * (candleWidth + 3) + candleWidth / 2;
                    const y = getY(c.vwap);
                    if (!startedVwap) {
                        ctx.moveTo(x, y);
                        startedVwap = true;
                    } else {
                        ctx.lineTo(x, y);
                    }
                }
            });
            ctx.stroke();
            ctx.setLineDash([]);

            // Draw Candlesticks
            candles.forEach((c, idx) => {
                const x = padding.left + idx * (candleWidth + 3);
                const isGreen = c.close >= c.open;
                const candleColor = isGreen ? "#00e699" : "#ff3366";

                // Wick
                ctx.strokeStyle = candleColor;
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.moveTo(x + candleWidth / 2, getY(c.high));
                ctx.lineTo(x + candleWidth / 2, getY(c.low));
                ctx.stroke();

                // Body
                const bodyTop = getY(Math.max(c.open, c.close));
                const bodyBottom = getY(Math.min(c.open, c.close));
                const bodyHeight = Math.max(2, bodyBottom - bodyTop);

                ctx.fillStyle = candleColor;
                ctx.fillRect(x, bodyTop, candleWidth, bodyHeight);
            });

            // Draw Proposal Trade Overlays (SL, Target, Entry)
            if (proposal && proposal.symbol === symbol) {
                ctx.lineWidth = 1.5;
                ctx.setLineDash([6, 3]);

                // Stop Loss (Red)
                const slY = getY(proposal.stop_loss);
                ctx.strokeStyle = "#ff3366";
                ctx.beginPath();
                ctx.moveTo(padding.left, slY);
                ctx.lineTo(width - padding.right, slY);
                ctx.stroke();
                ctx.fillStyle = "#ff3366";
                ctx.font = "10px 'JetBrains Mono', monospace";
                ctx.fillText(`SL: ₹${proposal.stop_loss}`, width - padding.right + 4, slY - 3);

                // Target 1 (Green)
                const tY = getY(proposal.target_1);
                ctx.strokeStyle = "#00e699";
                ctx.beginPath();
                ctx.moveTo(padding.left, tY);
                ctx.lineTo(width - padding.right, tY);
                ctx.stroke();
                ctx.fillStyle = "#00e699";
                ctx.fillText(`TP: ₹${proposal.target_1}`, width - padding.right + 4, tY - 3);

                // Entry Price (Gold)
                const entY = getY(proposal.entry_price);
                ctx.strokeStyle = "#ffb703";
                ctx.beginPath();
                ctx.moveTo(padding.left, entY);
                ctx.lineTo(width - padding.right, entY);
                ctx.stroke();
                ctx.fillStyle = "#ffb703";
                ctx.fillText(`ENTRY: ₹${proposal.entry_price}`, width - padding.right + 4, entY - 3);

                ctx.setLineDash([]);
            }
        };

        draw();
        window.addEventListener("resize", draw);
        return () => window.removeEventListener("resize", draw);
    }, [candles, proposal, symbol]);

    return (
        <div className="glass-panel" style={{ padding: "18px", marginBottom: "20px" }}>
            {/* Chart Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px", flexWrap: "wrap", gap: "10px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                    <h3 style={{ fontSize: "16px", fontWeight: 700 }}>{symbol} Real-Time Chart</h3>
                    <span style={{ fontSize: "12px", color: "var(--text-dim)" }}>5-Min Intraday Candles</span>
                </div>

                {/* Indicator Legend */}
                <div style={{ display: "flex", alignItems: "center", gap: "14px", fontSize: "11px", fontFamily: "var(--font-mono)" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "#00f0ff" }}>
                        <span style={{ width: "8px", height: "2px", backgroundColor: "#00f0ff" }}></span> EMA 9
                    </span>
                    <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "#ffb703" }}>
                        <span style={{ width: "8px", height: "2px", backgroundColor: "#ffb703" }}></span> EMA 21
                    </span>
                    <span style={{ display: "flex", alignItems: "center", gap: "4px", color: "#c084fc" }}>
                        <span style={{ width: "8px", height: "2px", backgroundColor: "#c084fc", borderBottom: "1px dashed" }}></span> VWAP
                    </span>
                </div>
            </div>

            {/* Canvas */}
            <div style={{ width: "100%", height: "320px", position: "relative", overflow: "hidden", borderRadius: "8px" }}>
                <canvas
                    ref={canvasRef}
                    style={{ width: "100%", height: "100%", display: "block" }}
                />
                {effectiveLoading && (
                    <div
                        style={{
                            position: "absolute",
                            top: 0,
                            left: 0,
                            right: 0,
                            bottom: 0,
                            backgroundColor: "rgba(10, 15, 26, 0.82)",
                            backdropFilter: "blur(6px)",
                            WebkitBackdropFilter: "blur(6px)",
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                            justifyContent: "center",
                            gap: "14px",
                            zIndex: 10,
                            animation: "fadeIn 0.2s ease"
                        }}
                    >
                        <div
                            style={{
                                width: "40px",
                                height: "40px",
                                border: "3px solid rgba(0, 240, 255, 0.15)",
                                borderTop: "3px solid #00f0ff",
                                borderRadius: "50%",
                                animation: "spin 0.75s linear infinite",
                                boxShadow: "0 0 15px rgba(0, 240, 255, 0.3)"
                            }}
                        />
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "5px", textAlign: "center" }}>
                            <span style={{ fontSize: "14px", fontWeight: 700, color: "#f8fafc", letterSpacing: "0.4px" }}>
                                Loading live chart data for {symbol}...
                            </span>
                            <span style={{ fontSize: "11px", color: "#94a3b8", fontFamily: "var(--font-mono)" }}>
                                Streaming real-time 5-min candles & technical indicators
                            </span>
                        </div>
                    </div>
                )}

                {/* Diagnostic Status Screen when candles are not loaded */}
                {!effectiveLoading && candles.length === 0 && (
                    <div
                        style={{
                            position: "absolute",
                            top: 0,
                            left: 0,
                            right: 0,
                            bottom: 0,
                            backgroundColor: "rgba(10, 15, 26, 0.94)",
                            backdropFilter: "blur(8px)",
                            WebkitBackdropFilter: "blur(8px)",
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                            justifyContent: "center",
                            padding: "24px",
                            textAlign: "center",
                            zIndex: 5
                        }}
                    >
                        {/* Condition A: Kite session is not initialized or not connected */}
                        {(!kiteConnected || effectiveStatus === "KITE_SESSION_NOT_INITIALIZED") && (
                            <div style={{ maxWidth: "480px", display: "flex", flexDirection: "column", alignItems: "center", gap: "12px" }}>
                                <div style={{ background: "rgba(255, 179, 0, 0.15)", padding: "14px", borderRadius: "16px", border: "1px solid rgba(255, 179, 0, 0.3)" }}>
                                    <ShieldAlert size={36} color="#ffb300" />
                                </div>
                                <div>
                                    <h4 style={{ fontSize: "16px", fontWeight: 700, color: "#ffb300", marginBottom: "6px" }}>
                                        Zerodha Kite Session Not Initialized
                                    </h4>
                                    <p style={{ fontSize: "13px", color: "#cbd5e1", lineHeight: 1.5 }}>
                                        Real-time candlestick charts cannot load without an authenticated Zerodha Kite session.
                                    </p>
                                    <p style={{ fontSize: "11.5px", color: "#94a3b8", marginTop: "6px", fontFamily: "var(--font-mono)" }}>
                                        Please authenticate your daily Kite token in settings.
                                    </p>
                                </div>
                                {onOpenSettings && (
                                    <button
                                        onClick={onOpenSettings}
                                        className="btn btn-primary"
                                        style={{
                                            marginTop: "4px",
                                            display: "flex",
                                            alignItems: "center",
                                            gap: "8px",
                                            padding: "8px 18px",
                                            fontSize: "13px",
                                            background: "#ffb300",
                                            color: "#0c111d",
                                            borderColor: "#ffb300"
                                        }}
                                    >
                                        <Settings size={15} />
                                        Open Settings to Authenticate
                                    </button>
                                )}
                            </div>
                        )}

                        {/* Condition B: Kite is connected, but Zerodha Kite returned an error from their side */}
                        {kiteConnected && effectiveStatus === "KITE_BROKER_ERROR" && (
                            <div style={{ maxWidth: "520px", display: "flex", flexDirection: "column", alignItems: "center", gap: "12px" }}>
                                <div style={{ background: "rgba(255, 51, 102, 0.15)", padding: "14px", borderRadius: "16px", border: "1px solid rgba(255, 51, 102, 0.35)" }}>
                                    <AlertTriangle size={36} color="#ff3366" />
                                </div>
                                <div>
                                    <h4 style={{ fontSize: "16px", fontWeight: 700, color: "#ff3366", marginBottom: "6px" }}>
                                        Zerodha Kite Broker Error
                                    </h4>
                                    <p style={{ fontSize: "13px", color: "#cbd5e1", lineHeight: 1.5 }}>
                                        Kite session is active, but Zerodha Kite returned an error while fetching 5-minute candles for <strong>{symbol}</strong>:
                                    </p>
                                    <div
                                        style={{
                                            marginTop: "8px",
                                            background: "rgba(0, 0, 0, 0.45)",
                                            border: "1px solid rgba(255, 51, 102, 0.3)",
                                            padding: "10px 14px",
                                            borderRadius: "8px",
                                            fontSize: "12px",
                                            color: "#fca5a5",
                                            fontFamily: "var(--font-mono)",
                                            wordBreak: "break-word"
                                        }}
                                    >
                                        {effectiveError || "Historical data API call failed or timed out from broker."}
                                    </div>
                                    <p style={{ fontSize: "11px", color: "#94a3b8", marginTop: "8px" }}>
                                        💡 Note: Zerodha requires an active <strong>Kite Connect Historical Data</strong> add-on subscription (₹2,000/mo) on your developer app to stream candlestick charts.
                                    </p>
                                </div>
                                {onRetry && (
                                    <button
                                        onClick={onRetry}
                                        className="btn btn-secondary"
                                        style={{
                                            marginTop: "4px",
                                            display: "flex",
                                            alignItems: "center",
                                            gap: "8px",
                                            padding: "8px 16px",
                                            fontSize: "13px"
                                        }}
                                    >
                                        <RefreshCw size={14} />
                                        Retry Fetching Candles
                                    </button>
                                )}
                            </div>
                        )}

                        {/* Condition C: Kite is connected, but no intraday candles returned (market closed, weekend, or holiday) */}
                        {kiteConnected && chartStatus !== "KITE_SESSION_NOT_INITIALIZED" && chartStatus !== "KITE_BROKER_ERROR" && (
                            <div style={{ maxWidth: "460px", display: "flex", flexDirection: "column", alignItems: "center", gap: "12px" }}>
                                <div style={{ background: "rgba(0, 240, 255, 0.12)", padding: "14px", borderRadius: "16px", border: "1px solid rgba(0, 240, 255, 0.25)" }}>
                                    <BarChart2 size={36} color="#00f0ff" />
                                </div>
                                <div>
                                    <h4 style={{ fontSize: "16px", fontWeight: 700, color: "#00f0ff", marginBottom: "6px" }}>
                                        No Market Candles Available for {symbol}
                                    </h4>
                                    <p style={{ fontSize: "13px", color: "#cbd5e1", lineHeight: 1.5 }}>
                                        {errorMessage || "No recent 5-minute candlestick data was returned by Zerodha Kite for this instrument. Market may be closed or trading is halted."}
                                    </p>
                                </div>
                                {onRetry && (
                                    <button
                                        onClick={onRetry}
                                        className="btn btn-secondary"
                                        style={{
                                            marginTop: "4px",
                                            display: "flex",
                                            alignItems: "center",
                                            gap: "8px",
                                            padding: "8px 16px",
                                            fontSize: "13px"
                                        }}
                                    >
                                        <RefreshCw size={14} />
                                        Refresh Candles
                                    </button>
                                )}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};
