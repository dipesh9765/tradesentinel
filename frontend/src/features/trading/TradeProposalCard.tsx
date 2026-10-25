import React from "react";
import { ArrowUpRight, ArrowDownRight, CheckCircle2, XCircle, Volume2, Sparkles, Clock, AlertTriangle, ShieldCheck } from "lucide-react";
import type { TradeProposal } from "../../types";
import { GenConsts, type TradingModeType } from "../../constants";

interface TradeProposalCardProps {
  proposal: TradeProposal | null;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onReplayAudio?: (text: string) => void;
  onTriggerScan?: (symbol: string) => void;
  onTriggerManualScan?: (symbol: string) => void;
  isScanning?: boolean;
  selectedSymbol?: string;
  tradingMode?: TradingModeType;
}

export const TradeProposalCard: React.FC<TradeProposalCardProps> = ({
  proposal,
  onApprove,
  onReject,
  onReplayAudio,
  onTriggerScan,
  onTriggerManualScan,
  isScanning = false,
  selectedSymbol = "",
  tradingMode = GenConsts.MODES.PAPER
}) => {
  if (!proposal || proposal.status !== GenConsts.STATUSES.PENDING_APPROVAL) {
    return (
      <div className="glass-panel" style={{ padding: "30px 24px", textAlign: "center", marginBottom: "20px" }}>
        <div style={{
          width: "56px",
          height: "56px",
          borderRadius: "16px",
          background: "rgba(0, 240, 255, 0.1)",
          border: "1px solid var(--border-glow)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          margin: "0 auto 16px auto"
        }}>
          <Sparkles size={28} color="var(--color-cyan)" />
        </div>
        <h3 style={{ fontSize: "18px", fontWeight: 700, marginBottom: "8px" }}>
          Rules-Based Market Scanner
        </h3>
        <p style={{ color: "var(--text-muted)", fontSize: "14px", maxWidth: "480px", margin: "0 auto 20px auto" }}>
          Run the multi-factor rules engine (EMA ribbon, Supertrend, VWAP, ADX, RSI, CPR) on <strong>{selectedSymbol}</strong> to look for a high-conviction intraday setup. An AI model only explains the result.
        </p>
        <button
          onClick={() => (onTriggerScan || onTriggerManualScan)?.(selectedSymbol)}
          disabled={isScanning}
          className="btn btn-primary"
          style={{ padding: "12px 28px", fontSize: "15px" }}
        >
          <Sparkles size={18} />
          <span>{isScanning ? `Analyzing ${selectedSymbol}...` : `Scan ${selectedSymbol}`}</span>
        </button>
      </div>
    );
  }

  const isBull = proposal.direction === GenConsts.DIRECTIONS.BULLISH;

  return (
    <div
      className={`glass-panel ${isBull ? "glow-bull" : "glow-bear"}`}
      style={{
        padding: "24px",
        marginBottom: "20px",
        border: `1px solid ${isBull ? "rgba(0, 230, 153, 0.4)" : "rgba(255, 51, 102, 0.4)"}`,
        position: "relative",
        overflow: "hidden"
      }}
    >
      {/* Expiry countdown bar */}
      <div
        className="countdown-bar"
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          height: "4px",
          background: isBull ? "var(--color-bull)" : "var(--color-bear)"
        }}
      />

      {/* Header Info */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "18px", flexWrap: "wrap", gap: "12px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
            <span
              style={{
                padding: "4px 10px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 800,
                letterSpacing: "0.5px",
                background: isBull ? "rgba(0, 230, 153, 0.15)" : "rgba(255, 51, 102, 0.15)",
                color: isBull ? "var(--color-bull)" : "var(--color-bear)",
                border: `1px solid ${isBull ? "rgba(0, 230, 153, 0.3)" : "rgba(255, 51, 102, 0.3)"}`,
                display: "inline-flex",
                alignItems: "center",
                gap: "4px"
              }}
            >
              {isBull ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
              {proposal.signal_type.replace("_", " ")}
            </span>
            <span style={{ fontSize: "11px", color: "var(--text-dim)", display: "flex", alignItems: "center", gap: "4px" }}>
              <Clock size={12} /> Awaiting Voice / Click Confirmation
            </span>
          </div>
          <h2 style={{ fontSize: "24px", fontWeight: 800, letterSpacing: "-0.5px" }}>
            {proposal.instrument}
          </h2>
        </div>

        {/* Confidence & Lot Size Badges */}
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <div style={{
            background: "rgba(255, 255, 255, 0.05)",
            padding: "6px 12px",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
            textAlign: "right"
          }}>
            <div style={{ fontSize: "10px", color: "var(--text-dim)", textTransform: "uppercase" }}>Test Lot Size</div>
            <div className="font-mono" style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-cyan)" }}>
              {proposal.lot_size} LOT (Safe)
            </div>
          </div>
          <div style={{
            background: "rgba(255, 255, 255, 0.05)",
            padding: "6px 12px",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
            textAlign: "right"
          }}>
            <div style={{ fontSize: "10px", color: "var(--text-dim)", textTransform: "uppercase" }}>AI Confidence</div>
            <div className="font-mono" style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-bull)" }}>
              {proposal.confidence}%
            </div>
          </div>
        </div>
      </div>

      {/* Grid of Key Price Levels */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
        gap: "12px",
        marginBottom: "20px"
      }}>
        <div className="glass-panel" style={{ padding: "12px", borderRadius: "10px", background: "rgba(0,0,0,0.3)" }}>
          <div style={{ fontSize: "11px", color: "var(--text-dim)" }}>ENTRY PRICE</div>
          <div className="font-mono" style={{ fontSize: "18px", fontWeight: 700, color: "var(--text-main)" }}>
            ₹{proposal.entry_price.toFixed(2)}
          </div>
        </div>
        <div className="glass-panel" style={{ padding: "12px", borderRadius: "10px", background: "rgba(255, 51, 102, 0.05)", borderColor: "rgba(255, 51, 102, 0.2)" }}>
          <div style={{ fontSize: "11px", color: "var(--color-bear)", fontWeight: 600 }}>STOP LOSS (SL)</div>
          <div className="font-mono" style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-bear)" }}>
            ₹{proposal.stop_loss.toFixed(2)}
          </div>
        </div>
        <div className="glass-panel" style={{ padding: "12px", borderRadius: "10px", background: "rgba(0, 230, 153, 0.05)", borderColor: "rgba(0, 230, 153, 0.2)" }}>
          <div style={{ fontSize: "11px", color: "var(--color-bull)", fontWeight: 600 }}>TARGET 1</div>
          <div className="font-mono" style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-bull)" }}>
            ₹{proposal.target_1.toFixed(2)}
          </div>
        </div>
        <div className="glass-panel" style={{ padding: "12px", borderRadius: "10px", background: "rgba(0, 240, 255, 0.05)", borderColor: "rgba(0, 240, 255, 0.2)" }}>
          <div style={{ fontSize: "11px", color: "var(--color-cyan)", fontWeight: 600 }}>RISK : REWARD</div>
          <div className="font-mono" style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-cyan)" }}>
            {proposal.risk_reward}
          </div>
        </div>
      </div>

      {/* Verbal Pitch & Rationale */}
      <div style={{
        background: "rgba(0, 0, 0, 0.35)",
        border: "1px solid var(--border-color)",
        borderRadius: "10px",
        padding: "14px 18px",
        marginBottom: "20px"
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
          <span style={{ fontSize: "12px", fontWeight: 700, color: "var(--color-cyan)", display: "flex", alignItems: "center", gap: "6px" }}>
            <Volume2 size={14} /> AI Recommendation Rationale
          </span>
          {onReplayAudio && proposal.verbal_pitch && (
            <button
              onClick={() => onReplayAudio(proposal.verbal_pitch || "")}
              className="btn btn-secondary"
              style={{ padding: "4px 8px", fontSize: "11px" }}
              title="Hear this trade setup again"
            >
              Replay Voice
            </button>
          )}
        </div>
        <p style={{ fontSize: "13px", color: "var(--text-main)", fontStyle: "italic", marginBottom: "6px" }}>
          "{proposal.reasoning || proposal.verbal_pitch || "Quantitative A+ Setup Triggered."}"
        </p>
        <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
          <strong>Technical Rationale:</strong> {proposal.technical_rationale}
        </div>
      </div>

      {/* Execution Mode Notice */}
      <div style={{
        padding: "10px 14px",
        borderRadius: "8px",
        marginBottom: "16px",
        display: "flex",
        alignItems: "center",
        gap: "10px",
        background: tradingMode === "LIVE" ? "rgba(255, 59, 48, 0.12)" : "rgba(0, 240, 255, 0.08)",
        border: `1px solid ${tradingMode === "LIVE" ? "rgba(255, 59, 48, 0.4)" : "rgba(0, 240, 255, 0.25)"}`,
        fontSize: "12px",
        fontWeight: 600,
        color: tradingMode === "LIVE" ? "#ff8080" : "var(--color-cyan)"
      }}>
        {tradingMode === "LIVE" ? (
          <>
            <AlertTriangle size={16} color="#ff4d4f" />
            <span>
              <strong>⚡ LIVE ORDER WARNING:</strong> Approving will immediately send a real MIS order to <strong>Zerodha Kite</strong> using live funds!
            </span>
          </>
        ) : (
          <>
            <ShieldCheck size={16} color="var(--color-cyan)" />
            <span>
              <strong>🧪 SANDBOX SIMULATION:</strong> Approving will execute a virtual paper trade safely. No real money or broker orders will be sent.
            </span>
          </>
        )}
      </div>

      {/* Action Confirmation Buttons */}
      <div style={{ display: "flex", gap: "14px" }}>
        <button
          onClick={() => onApprove(proposal.proposal_id)}
          className={`btn ${isBull ? "btn-bull" : "btn-primary"}`}
          style={{ flex: 1, padding: "14px 20px", fontSize: "15px" }}
        >
          <CheckCircle2 size={20} />
          <span>Approve & Place Order (Say "Approve")</span>
        </button>
        <button
          onClick={() => onReject(proposal.proposal_id)}
          className="btn btn-secondary"
          style={{ padding: "14px 24px", fontSize: "15px", color: "var(--color-bear)", borderColor: "rgba(255, 51, 102, 0.2)" }}
        >
          <XCircle size={20} />
          <span>Pass (Say "Reject")</span>
        </button>
      </div>
    </div>
  );
};
