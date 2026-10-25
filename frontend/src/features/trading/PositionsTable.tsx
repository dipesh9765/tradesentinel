import React, { useState } from "react";
import type { Position, OrderRecord, HistoryItem } from "../../types";
import { HistoryTracker } from "./HistoryTracker";

interface PositionsTableProps {
  positions: Position[];
  orders: OrderRecord[];
  history: HistoryItem[];
  onClosePosition: (id: string) => void;
  onRefreshHistory?: () => void;
}

export const PositionsTable: React.FC<PositionsTableProps> = ({
  positions,
  orders,
  history,
  onClosePosition,
  onRefreshHistory = () => {}
}) => {
  const [activeTab, setActiveTab] = useState<"positions" | "history" | "orders">("history");

  return (
    <div className="glass-panel" style={{ padding: "18px" }}>
      {/* Tabs */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px", borderBottom: "1px solid var(--border-color)", paddingBottom: "10px", flexWrap: "wrap", gap: "10px" }}>
        <div style={{ display: "flex", gap: "14px", flexWrap: "wrap" }}>
          <button
            onClick={() => setActiveTab("history")}
            style={{
              background: "none",
              border: "none",
              fontSize: "14px",
              fontWeight: 700,
              cursor: "pointer",
              color: activeTab === "history" ? "var(--color-cyan)" : "var(--text-muted)",
              borderBottom: activeTab === "history" ? "2px solid var(--color-cyan)" : "none",
              paddingBottom: "6px"
            }}
          >
            History & Real-Time Tracker ({history.length})
          </button>
          <button
            onClick={() => setActiveTab("positions")}
            style={{
              background: "none",
              border: "none",
              fontSize: "14px",
              fontWeight: 700,
              cursor: "pointer",
              color: activeTab === "positions" ? "var(--color-cyan)" : "var(--text-muted)",
              borderBottom: activeTab === "positions" ? "2px solid var(--color-cyan)" : "none",
              paddingBottom: "6px"
            }}
          >
            Active Positions ({positions.length})
          </button>
          <button
            onClick={() => setActiveTab("orders")}
            style={{
              background: "none",
              border: "none",
              fontSize: "14px",
              fontWeight: 700,
              cursor: "pointer",
              color: activeTab === "orders" ? "var(--color-cyan)" : "var(--text-muted)",
              borderBottom: activeTab === "orders" ? "2px solid var(--color-cyan)" : "none",
              paddingBottom: "6px"
            }}
          >
            Order Log ({orders.length})
          </button>
        </div>

        <span style={{ fontSize: "11px", color: "var(--text-dim)" }}>
          SQLite Persistent Storage
        </span>
      </div>

      {/* History & Real-Time Tracker Tab */}
      {activeTab === "history" && (
        <HistoryTracker
          history={history}
          onClosePosition={onClosePosition}
          onRefreshHistory={onRefreshHistory}
        />
      )}

      {/* Active Positions Tab */}
      {activeTab === "positions" && (
        <div>
          {positions.length === 0 ? (
            <div style={{ textAlign: "center", padding: "30px 10px", color: "var(--text-muted)", fontSize: "13px" }}>
              No open intraday positions. Approve an AI trade recommendation or scan a symbol above.
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "13px" }}>
                <thead>
                  <tr style={{ color: "var(--text-dim)", borderBottom: "1px solid var(--border-color)" }}>
                    <th style={{ padding: "8px 10px" }}>Instrument</th>
                    <th style={{ padding: "8px 10px" }}>Qty</th>
                    <th style={{ padding: "8px 10px" }}>Buy Price</th>
                    <th style={{ padding: "8px 10px" }}>LTP</th>
                    <th style={{ padding: "8px 10px" }}>SL / Target</th>
                    <th style={{ padding: "8px 10px", textAlign: "right" }}>P&L (₹)</th>
                    <th style={{ padding: "8px 10px", textAlign: "center" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((pos) => {
                    const isProfit = pos.unrealized_pnl >= 0;
                    return (
                      <tr key={pos.position_id} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                        <td style={{ padding: "12px 10px", fontWeight: 700 }}>
                          <div>{pos.instrument}</div>
                          <div style={{ fontSize: "10px", color: "var(--text-dim)" }}>{pos.opened_at} • {pos.mode}</div>
                        </td>
                        <td className="font-mono" style={{ padding: "12px 10px" }}>{pos.quantity} Lot</td>
                        <td className="font-mono" style={{ padding: "12px 10px" }}>₹{pos.buy_price.toFixed(2)}</td>
                        <td className="font-mono" style={{ padding: "12px 10px", fontWeight: 600 }}>₹{pos.current_ltp.toFixed(2)}</td>
                        <td className="font-mono" style={{ padding: "12px 10px", fontSize: "11px" }}>
                          <span style={{ color: "var(--color-bear)" }}>SL: ₹{pos.stop_loss}</span>
                          <span style={{ margin: "0 4px" }}>|</span>
                          <span style={{ color: "var(--color-bull)" }}>TP: ₹{pos.target_1}</span>
                        </td>
                        <td className="font-mono" style={{ padding: "12px 10px", textAlign: "right", fontWeight: 700, color: isProfit ? "var(--color-bull)" : "var(--color-bear)" }}>
                          {isProfit ? "+" : ""}₹{pos.unrealized_pnl.toFixed(2)}
                          <div style={{ fontSize: "10px" }}>({isProfit ? "+" : ""}{pos.pnl_pct}%)</div>
                        </td>
                        <td style={{ padding: "12px 10px", textAlign: "center" }}>
                          <button
                            onClick={() => onClosePosition(pos.position_id)}
                            className="btn btn-secondary"
                            style={{ padding: "5px 10px", fontSize: "11px", color: "var(--color-bear)", borderColor: "rgba(255,51,102,0.3)" }}
                          >
                            Exit
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Order Log Content */}
      {activeTab === "orders" && (
        <div style={{ maxHeight: "240px", overflowY: "auto" }}>
          {orders.length === 0 ? (
            <div style={{ textAlign: "center", padding: "30px 10px", color: "var(--text-muted)", fontSize: "13px" }}>
              No orders executed yet.
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "13px" }}>
              <thead>
                <tr style={{ color: "var(--text-dim)", borderBottom: "1px solid var(--border-color)" }}>
                  <th style={{ padding: "6px 10px" }}>Time</th>
                  <th style={{ padding: "6px 10px" }}>Instrument</th>
                  <th style={{ padding: "6px 10px" }}>Type</th>
                  <th style={{ padding: "6px 10px" }}>Price</th>
                  <th style={{ padding: "6px 10px" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o, idx) => (
                  <tr key={idx} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                    <td className="font-mono" style={{ padding: "8px 10px", fontSize: "11px", color: "var(--text-dim)" }}>{o.timestamp}</td>
                    <td style={{ padding: "8px 10px", fontWeight: 600 }}>{o.instrument}</td>
                    <td className="font-mono" style={{ padding: "8px 10px", color: o.type === "BUY" ? "var(--color-bull)" : "var(--color-bear)" }}>{o.type}</td>
                    <td className="font-mono" style={{ padding: "8px 10px" }}>₹{o.price.toFixed(2)}</td>
                    <td style={{ padding: "8px 10px", fontSize: "11px" }}>
                      <span style={{ padding: "2px 6px", borderRadius: "4px", background: "rgba(0, 230, 153, 0.15)", color: "var(--color-bull)" }}>
                        {o.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};
