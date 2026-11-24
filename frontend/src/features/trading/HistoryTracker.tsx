import React, { useState } from "react";
import { ChevronDown, ChevronUp, ArrowUpRight, ArrowDownRight, LogOut } from "lucide-react";
import type { HistoryItem } from "../../types";

interface HistoryTrackerProps {
    history: HistoryItem[];
    onClosePosition: (positionId: string) => void;
    onRefreshHistory: () => void;
}

export const HistoryTracker: React.FC<HistoryTrackerProps> = ({
    history,
    onClosePosition
}) => {
    const [filter, setFilter] = useState<"ALL" | "APPROVED" | "OPEN" | "CLOSED" | "REJECTED">("ALL");
    const [expandedId, setExpandedId] = useState<string | null>(null);

    const filteredHistory = history.filter((item) => {
        if (filter === "ALL") return true;
        if (filter === "OPEN") return item.overall_status === "OPEN";
        if (filter === "CLOSED") return item.overall_status === "CLOSED";
        if (filter === "APPROVED") return item.overall_status === "OPEN" || item.overall_status === "CLOSED" || item.overall_status === "APPROVED";
        if (filter === "REJECTED") return item.overall_status === "REJECTED";
        return true;
    });

    const toggleExpand = (proposalId: string) => {
        setExpandedId(expandedId === proposalId ? null : proposalId);
    };

    return (
        <div className="glass-panel" style={{ padding: "18px" }}>
            {/* Header & Filter Tabs */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
                <div>
                    <h3 style={{ fontSize: "16px", fontWeight: 700 }}>Signals & Order History Tracker</h3>
                    <div style={{ fontSize: "12px", color: "var(--color-ink-faint)" }}>
                        Persisted in SQLite Database, Track real-time progress, SL, targets, and exit anytime
                    </div>
                </div>

                {/* Filters */}
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                    {(["ALL", "OPEN", "CLOSED", "REJECTED"] as const).map((f) => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            style={{
                                background: filter === f ? "color-mix(in srgb, var(--color-signal) 15%, transparent)" : "color-mix(in srgb, var(--color-ink) 4%, transparent)",
                                color: filter === f ? "var(--color-signal)" : "var(--color-ink-soft)",
                                border: `1px solid ${filter === f ? "var(--color-edge)" : "var(--color-line)"}`,
                                borderRadius: "6px",
                                padding: "4px 10px",
                                fontSize: "12px",
                                fontWeight: 600,
                                cursor: "pointer"
                            }}
                        >
                            {f === "ALL" ? `All (${history.length})` : f}
                        </button>
                    ))}
                </div>
            </div>

            {/* History Items List */}
            {filteredHistory.length === 0 ? (
                <div style={{ textAlign: "center", padding: "30px 10px", color: "var(--color-ink-soft)", fontSize: "13px" }}>
                    No records match this filter. Trigger a scan above to generate signals.
                </div>
            ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                    {filteredHistory.map((item) => {
                        const isExpanded = expandedId === item.proposal_id;
                        const isBull = item.direction === "BULLISH";
                        const isOpen = item.overall_status === "OPEN";
                        const isClosed = item.overall_status === "CLOSED";
                        const isRejected = item.overall_status === "REJECTED";

                        const pnl = isOpen ? (item.unrealized_pnl || 0) : (item.realized_pnl || 0);
                        const isProfit = pnl >= 0;

                        // Compute Progress towards Target or SL
                        const cur = item.current_ltp || item.buy_price || item.entry_price;
                        const entry = item.buy_price || item.entry_price;
                        const sl = item.stop_loss;
                        const tp = item.target_1;

                        const totalRange = Math.abs(tp - sl) || 1;
                        const progressPct = Math.min(100, Math.max(0, ((cur - sl) / totalRange) * 100));

                        return (
                            <div
                                key={item.proposal_id}
                                style={{
                                    borderRadius: "10px",
                                    background: isExpanded ? "color-mix(in srgb, var(--color-ink) 5%, transparent)" : "color-mix(in srgb, var(--color-ink) 2%, transparent)",
                                    border: `1px solid ${isOpen ? "color-mix(in srgb, var(--color-ok) 30%, transparent)" : isExpanded ? "var(--color-edge)" : "var(--color-line)"}`,
                                    overflow: "hidden",
                                    transition: "background-color 160ms, border-color 160ms, color 160ms, opacity 160ms"
                                }}
                            >
                                {/* Summary Row (Clickable) */}
                                <div
                                    onClick={() => toggleExpand(item.proposal_id)}
                                    style={{
                                        padding: "12px 16px",
                                        display: "flex",
                                        justifyContent: "space-between",
                                        alignItems: "center",
                                        cursor: "pointer",
                                        userSelect: "none"
                                    }}
                                >
                                    <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                                        {/* Direction Badge */}
                                        <span
                                            style={{
                                                padding: "3px 8px",
                                                borderRadius: "5px",
                                                fontSize: "12px",
                                                fontWeight: 700,
                                                background: isBull ? "color-mix(in srgb, var(--color-ok) 15%, transparent)" : "color-mix(in srgb, var(--color-bad) 15%, transparent)",
                                                color: isBull ? "var(--color-ok)" : "var(--color-bad)",
                                                display: "flex",
                                                alignItems: "center",
                                                gap: "4px"
                                            }}
                                        >
                                            {isBull ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                                            {item.signal_type.replace("_", " ")}
                                        </span>

                                        <div>
                                            <div style={{ fontWeight: 700, fontSize: "14px" }}>{item.instrument}</div>
                                            <div style={{ fontSize: "12px", color: "var(--color-ink-faint)" }}>
                                                {item.suggested_at}, Entry: ₹{item.entry_price}
                                            </div>
                                        </div>
                                    </div>

                                    {/* Status & Realized Net Gain */}
                                    <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
                                        {isOpen && (
                                            <div style={{ textAlign: "right" }}>
                                                <div style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "12px", fontWeight: 700, color: item.mode === "PAPER" ? "var(--color-signal)" : "var(--color-ok)", background: item.mode === "PAPER" ? "color-mix(in srgb, var(--color-signal) 15%, transparent)" : "color-mix(in srgb, var(--color-ok) 15%, transparent)", padding: "2px 8px", borderRadius: "12px" }}>
                                                    <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: item.mode === "PAPER" ? "var(--color-signal)" : "var(--color-ok)" }} className="radar-active" />
                                                    {item.mode === "PAPER" ? "SANDBOX OPEN" : "LIVE OPEN"}
                                                </div>
                                                <div className="font-mono" style={{ fontSize: "13px", fontWeight: 700, color: isProfit ? "var(--color-ok)" : "var(--color-bad)", marginTop: "2px" }}>
                                                    {isProfit ? "+" : ""}₹{pnl.toFixed(2)} ({isProfit ? "+" : ""}{item.pnl_pct || 0}%)
                                                </div>
                                            </div>
                                        )}

                                        {isClosed && (
                                            <div style={{ textAlign: "right" }}>
                                                <div style={{ fontSize: "12px", color: "var(--color-ink-faint)", }}>
                                                    Net Gain
                                                </div>
                                                <div className="font-mono" style={{ fontSize: "14px", fontWeight: 700, color: isProfit ? "var(--color-ok)" : "var(--color-bad)" }}>
                                                    {isProfit ? "+" : ""}₹{pnl.toFixed(2)}
                                                </div>
                                            </div>
                                        )}

                                        {isRejected && (
                                            <span style={{ fontSize: "12px", color: "var(--color-ink-faint)", background: "color-mix(in srgb, var(--color-ink) 5%, transparent)", padding: "3px 8px", borderRadius: "6px" }}>
                                                REJECTED
                                            </span>
                                        )}

                                        {item.overall_status === "PENDING" && (
                                            <span style={{ fontSize: "12px", color: "var(--color-warn)", background: "color-mix(in srgb, var(--color-warn) 12%, transparent)", padding: "3px 8px", borderRadius: "6px" }}>
                                                PENDING
                                            </span>
                                        )}

                                        {isExpanded ? <ChevronUp size={16} color="var(--color-ink-faint)" /> : <ChevronDown size={16} color="var(--color-ink-faint)" />}
                                    </div>
                                </div>

                                {/* Expanded Real-Time Tracker */}
                                {isExpanded && (
                                    <div style={{ padding: "16px", borderTop: "1px solid var(--color-line)", background: "color-mix(in srgb, var(--color-ink) 25%, transparent)" }}>
                                        {/* Visual Target & Stop-Loss Tracker Bar */}
                                        <div style={{ marginBottom: "16px" }}>
                                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "6px", fontFamily: "var(--font-data)" }}>
                                                <span style={{ color: "var(--color-bad)", fontWeight: 600 }}>SL: ₹{item.stop_loss}</span>
                                                <span style={{ color: "var(--color-signal)", fontWeight: 700 }}>
                                                    Current LTP: ₹{cur.toFixed(2)}
                                                </span>
                                                <span style={{ color: "var(--color-ok)", fontWeight: 600 }}>Target 1: ₹{item.target_1}</span>
                                            </div>

                                            {/* Progress bar */}
                                            <div style={{ width: "100%", height: "8px", background: "color-mix(in srgb, var(--color-ink) 8%, transparent)", borderRadius: "4px", overflow: "hidden", position: "relative" }}>
                                                <div
                                                    style={{
                                                        width: `${progressPct}%`,
                                                        height: "100%",
                                                        background: isProfit
                                                            ? "var(--color-warn)"
                                                            : "var(--color-bad)",
                                                        transition: "width 0.3s ease"
                                                    }}
                                                />
                                            </div>
                                        </div>

                                        {/* Metrics Grid */}
                                        <div style={{
                                            display: "grid",
                                            gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
                                            gap: "10px",
                                            marginBottom: "14px"
                                        }}>
                                            <div className="glass-panel" style={{ padding: "8px 12px", borderRadius: "8px" }}>
                                                <div style={{ fontSize: "12px", color: "var(--color-ink-faint)" }}>BUY / ENTRY</div>
                                                <div className="font-mono" style={{ fontSize: "14px", fontWeight: 700 }}>₹{entry.toFixed(2)}</div>
                                            </div>
                                            <div className="glass-panel" style={{ padding: "8px 12px", borderRadius: "8px" }}>
                                                <div style={{ fontSize: "12px", color: "var(--color-ink-faint)" }}>Current price</div>
                                                <div className="font-mono" style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-signal)" }}>₹{cur.toFixed(2)}</div>
                                            </div>
                                            <div className="glass-panel" style={{ padding: "8px 12px", borderRadius: "8px" }}>
                                                <div style={{ fontSize: "12px", color: "var(--color-bad)" }}>Stop loss</div>
                                                <div className="font-mono" style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-bad)" }}>₹{item.stop_loss}</div>
                                            </div>
                                            <div className="glass-panel" style={{ padding: "8px 12px", borderRadius: "8px" }}>
                                                <div style={{ fontSize: "12px", color: "var(--color-ok)" }}>Target 1</div>
                                                <div className="font-mono" style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-ok)" }}>₹{item.target_1}</div>
                                            </div>
                                            <div className="glass-panel" style={{ padding: "8px 12px", borderRadius: "8px" }}>
                                                <div style={{ fontSize: "12px", color: isProfit ? "var(--color-ok)" : "var(--color-bad)" }}>
                                                    {isOpen ? "Unrealized P&L" : "Net gain"}
                                                </div>
                                                <div className="font-mono" style={{ fontSize: "14px", fontWeight: 700, color: isProfit ? "var(--color-ok)" : "var(--color-bad)" }}>
                                                    {isProfit ? "+" : ""}₹{pnl.toFixed(2)}
                                                </div>
                                            </div>
                                        </div>

                                        {/* Metadata & Technical Rationale */}
                                        <div style={{ fontSize: "12px", color: "var(--color-ink-soft)", marginBottom: "12px", background: "color-mix(in srgb, var(--color-ink) 20%, transparent)", padding: "10px", borderRadius: "6px" }}>
                                            {item.close_reason && (
                                                <div style={{ marginBottom: "4px", color: "var(--color-ink)" }}>
                                                    <strong>Exit Reason:</strong> <span style={{ color: item.close_reason.includes("TARGET") ? "var(--color-ok)" : "var(--color-warn)" }}>{item.close_reason.replace("_", " ")}</span> ({item.closed_at})
                                                </div>
                                            )}
                                            <div><strong>AI Rationale:</strong> {item.technical_rationale || "EMA alignment and VWAP confirmation."}</div>
                                        </div>

                                        {/* Immediate Exit Button for Open Trades */}
                                        {isOpen && item.position_id && (
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    onClosePosition(item.position_id!);
                                                }}
                                                className="btn btn-bear"
                                                style={{ width: "100%", padding: "10px", fontSize: "13px" }}
                                            >
                                                <LogOut size={16} />
                                                <span>Exit Position Immediately (Sell @ ₹{cur.toFixed(2)})</span>
                                            </button>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};
