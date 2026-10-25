import React from "react";
import { Sparkles, TrendingUp, TrendingDown } from "lucide-react";
import type { Quote } from "../../types";

interface WatchlistProps {
  quotes: Quote[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  onScanSymbol?: (symbol: string) => void;
  isScanning?: boolean;
}

export const Watchlist: React.FC<WatchlistProps> = ({
  quotes,
  selectedSymbol,
  onSelectSymbol,
  onScanSymbol,
  isScanning = false
}) => {
  return (
    <div className="glass-panel" style={{ padding: "18px", height: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
        <h3 style={{ fontSize: "16px", fontWeight: 700 }}>Market Watch</h3>
        <span style={{ fontSize: "11px", color: "var(--text-dim)", textTransform: "uppercase" }}>
          Reliable Blue-Chips & Indices
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {quotes.map((quote) => {
          const isSelected = quote.symbol === selectedSymbol;
          const isBull = quote.change >= 0;

          return (
            <div
              key={quote.symbol}
              onClick={() => onSelectSymbol(quote.symbol)}
              style={{
                padding: "10px 14px",
                borderRadius: "10px",
                background: isSelected ? "rgba(0, 240, 255, 0.08)" : "rgba(255, 255, 255, 0.03)",
                border: `1px solid ${isSelected ? "var(--border-glow)" : "var(--border-color)"}`,
                cursor: "pointer",
                transition: "all 0.2s ease",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center"
              }}
            >
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span style={{ fontWeight: 700, fontSize: "14px", color: isSelected ? "var(--color-cyan)" : "var(--text-main)" }}>
                    {quote.symbol}
                  </span>
                  {quote.call_option && (
                    <span style={{ fontSize: "9px", background: "rgba(168, 85, 247, 0.2)", color: "#c084fc", padding: "1px 4px", borderRadius: "3px" }}>
                      OPT
                    </span>
                  )}
                </div>

                {quote.call_option && quote.put_option && (
                  <div style={{ fontSize: "10px", color: "var(--text-dim)", marginTop: "2px", display: "flex", gap: "6px" }}>
                    <span>CE: ₹{quote.call_option.ltp}</span>
                    <span>•</span>
                    <span>PE: ₹{quote.put_option.ltp}</span>
                  </div>
                )}
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <div style={{ textAlign: "right" }}>
                  <div className="font-mono" style={{ fontSize: "14px", fontWeight: 700 }}>
                    ₹{quote.ltp.toLocaleString("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 2 })}
                  </div>
                  <div
                    className="font-mono"
                    style={{
                      fontSize: "11px",
                      fontWeight: 600,
                      color: isBull ? "var(--color-bull)" : "var(--color-bear)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "flex-end",
                      gap: "2px"
                    }}
                  >
                    {isBull ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
                    <span>{isBull ? "+" : ""}{quote.change_pct}%</span>
                  </div>
                </div>

                {/* Direct AI Scan button per entity */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onScanSymbol?.(quote.symbol);
                  }}
                  disabled={isScanning}
                  className="btn btn-secondary"
                  style={{
                    padding: "6px 8px",
                    borderRadius: "6px",
                    borderColor: isSelected ? "var(--border-glow)" : undefined
                  }}
                  title={`Scan ${quote.symbol} with Gemini`}
                >
                  <Sparkles size={13} color="var(--color-cyan)" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
