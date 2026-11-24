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
          background: "color-mix(in srgb, var(--color-signal) 10%, transparent)",
          border: "1px solid var(--color-edge)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          margin: "0 auto 16px auto"
        }}>
          <Sparkles size={28} color="var(--color-signal)" />
        </div>
        <h3 style={{ fontSize: "18px", fontWeight: 700, marginBottom: "8px" }}>
          Rules-Based Market Scanner
        </h3>
        <p style={{ color: "var(--color-ink-soft)", fontSize: "14px", maxWidth: "480px", margin: "0 auto 20px auto" }}>
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
        border: `1px solid ${isBull ? "color-mix(in srgb, var(--color-ok) 40%, transparent)" : "color-mix(in srgb, var(--color-bad) 40%, transparent)"}`,
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
          background: isBull ? "var(--color-ok)" : "var(--color-bad)"
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
                background: isBull ? "color-mix(in srgb, var(--color-ok) 15%, transparent)" : "color-mix(in srgb, var(--color-bad) 15%, transparent)",
                color: isBull ? "var(--color-ok)" : "var(--color-bad)",
                border: `1px solid ${isBull ? "color-mix(in srgb, var(--color-ok) 30%, transparent)" : "color-mix(in srgb, var(--color-bad) 30%, transparent)"}`,
                display: "inline-flex",
                alignItems: "center",
                gap: "4px"
              }}
            >
              {isBull ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
              {proposal.signal_type.replace("_", " ")}
            </span>
            <span style={{ fontSize: "12px", color: "var(--color-ink-faint)", display: "flex", alignItems: "center", gap: "4px" }}>
              <Clock size={12} /> Awaiting Voice / Click Confirmation
            </span>
          </div>
          <h2 style={{ fontSize: "24px", fontWeight: 800, }}>
            {proposal.instrument}
          </h2>
        </div>

        {/* Confidence & Lot Size Badges */}
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <div style={{
            background: "color-mix(in srgb, var(--color-ink) 5%, transparent)",
            padding: "6px 12px",
            borderRadius: "8px",
            border: "1px solid var(--color-line)",
            textAlign: "right"
          }}>
            <div style={{ fontSize: "12px", color: "var(--color-ink-faint)", }}>Test Lot Size</div>
            <div className="font-mono" style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-signal)" }}>
              {proposal.lot_size} LOT (Safe)
            </div>
          </div>
          <div style={{
            background: "color-mix(in srgb, var(--color-ink) 5%, transparent)",
            padding: "6px 12px",
            borderRadius: "8px",
            border: "1px solid var(--color-line)",
            textAlign: "right"
          }}>
            <div style={{ fontSize: "12px", color: "var(--color-ink-faint)", }}>AI Confidence</div>
            <div className="font-mono" style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-ok)" }}>
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
        <div className="glass-panel" style={{ padding: "12px", borderRadius: "10px", background: "color-mix(in srgb, var(--color-ink) 30%, transparent)" }}>
          <div style={{ fontSize: "12px", color: "var(--color-ink-faint)" }}>Entry price</div>
          <div className="font-mono" style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-ink)" }}>
            ₹{proposal.entry_price.toFixed(2)}
          </div>
        </div>
        <div className="glass-panel" style={{ padding: "12px", borderRadius: "10px", background: "color-mix(in srgb, var(--color-bad) 5%, transparent)", borderColor: "color-mix(in srgb, var(--color-bad) 20%, transparent)" }}>
          <div style={{ fontSize: "12px", color: "var(--color-bad)", fontWeight: 600 }}>Stop loss</div>
          <div className="font-mono" style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-bad)" }}>
            ₹{proposal.stop_loss.toFixed(2)}
          </div>
        </div>
        <div className="glass-panel" style={{ padding: "12px", borderRadius: "10px", background: "color-mix(in srgb, var(--color-ok) 5%, transparent)", borderColor: "color-mix(in srgb, var(--color-ok) 20%, transparent)" }}>
          <div style={{ fontSize: "12px", color: "var(--color-ok)", fontWeight: 600 }}>Target 1</div>
          <div className="font-mono" style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-ok)" }}>
            ₹{proposal.target_1.toFixed(2)}
          </div>
        </div>
        <div className="glass-panel" style={{ padding: "12px", borderRadius: "10px", background: "color-mix(in srgb, var(--color-signal) 5%, transparent)", borderColor: "color-mix(in srgb, var(--color-signal) 20%, transparent)" }}>
          <div style={{ fontSize: "12px", color: "var(--color-signal)", fontWeight: 600 }}>RISK : REWARD</div>
          <div className="font-mono" style={{ fontSize: "18px", fontWeight: 700, color: "var(--color-signal)" }}>
            {proposal.risk_reward}
          </div>
        </div>
      </div>

      {/* Verbal Pitch & Rationale */}
      <div style={{
        background: "color-mix(in srgb, var(--color-ink) 35%, transparent)",
        border: "1px solid var(--color-line)",
        borderRadius: "10px",
        padding: "14px 18px",
        marginBottom: "20px"
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
          <span style={{ fontSize: "12px", fontWeight: 700, color: "var(--color-signal)", display: "flex", alignItems: "center", gap: "6px" }}>
            <Volume2 size={14} /> AI Recommendation Rationale
          </span>
          {onReplayAudio && proposal.verbal_pitch && (
            <button
              onClick={() => onReplayAudio(proposal.verbal_pitch || "")}
              className="btn btn-secondary"
              style={{ padding: "4px 8px", fontSize: "12px" }}
              title="Hear this trade setup again"
            >
              Replay Voice
            </button>
          )}
        </div>
        <p style={{ fontSize: "13px", color: "var(--color-ink)", fontStyle: "italic", marginBottom: "6px" }}>
          "{proposal.reasoning || proposal.verbal_pitch || "Quantitative A+ Setup Triggered."}"
        </p>
        <div style={{ fontSize: "12px", color: "var(--color-ink-soft)" }}>
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
        background: tradingMode === "LIVE" ? "color-mix(in srgb, var(--color-bad) 12%, transparent)" : "color-mix(in srgb, var(--color-signal) 8%, transparent)",
        border: `1px solid ${tradingMode === "LIVE" ? "color-mix(in srgb, var(--color-bad) 40%, transparent)" : "color-mix(in srgb, var(--color-signal) 25%, transparent)"}`,
        fontSize: "12px",
        fontWeight: 600,
        color: tradingMode === "LIVE" ? "var(--color-bad)" : "var(--color-signal)"
      }}>
        {tradingMode === "LIVE" ? (
          <>
            <AlertTriangle size={16} color="var(--color-bad)" />
            <span>
              <strong>Live order:</strong> Approving will immediately send a real MIS order to <strong>Zerodha Kite</strong> using live funds!
            </span>
          </>
        ) : (
          <>
            <ShieldCheck size={16} color="var(--color-signal)" />
            <span>
              <strong>Sandbox:</strong> Approving will execute a virtual paper trade safely. No real money or broker orders will be sent.
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
          style={{ padding: "14px 24px", fontSize: "15px", color: "var(--color-bad)", borderColor: "color-mix(in srgb, var(--color-bad) 20%, transparent)" }}
        >
          <XCircle size={20} />
          <span>Pass (Say "Reject")</span>
        </button>
      </div>
    </div>
  );
};
