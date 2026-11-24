import React from "react";
import { Mic, Volume2, MessageSquare, Briefcase, Keyboard, CheckCircle, XCircle } from "lucide-react";

interface VoiceRadarProps {
  isListening: boolean;
  transcript: string;
  isSpeaking: boolean;
  onSimulateCommand: (cmdText: string) => void;
  officeMode: boolean;
}

export const VoiceRadar: React.FC<VoiceRadarProps> = ({
  isListening,
  transcript,
  isSpeaking,
  onSimulateCommand,
  officeMode
}) => {
  if (officeMode) {
    return (
      <div className="glass-panel" style={{
        padding: "12px 20px",
        marginBottom: "20px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: "14px",
        background: "var(--color-raised)",
        borderColor: "color-mix(in srgb, var(--color-signal) 20%, transparent)"
      }}>
        {/* Office Silent Mode Indicator */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div style={{
            width: "36px",
            height: "36px",
            borderRadius: "50%",
            background: "color-mix(in srgb, var(--color-signal) 12%, transparent)",
            border: "1px solid var(--color-edge)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center"
          }}>
            <Briefcase size={18} color="var(--color-signal)" />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontSize: "13px", fontWeight: 700, color: "var(--color-signal)" }}>
                Office Silent Mode Active
              </span>
              <span style={{ fontSize: "12px", background: "color-mix(in srgb, var(--color-ok) 15%, transparent)", color: "var(--color-ok)", padding: "1px 6px", borderRadius: "4px" }}>
                Discreet
              </span>
            </div>
            <div style={{ fontSize: "12px", color: "var(--color-ink-soft)", marginTop: "2px" }}>
              Voice is muted. Notifications will pop up as Windows alerts, Telegram, or Discord.
            </div>
          </div>
        </div>

        {/* Quick Keyboard Hotkeys Pill */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            background: "color-mix(in srgb, var(--color-ink) 35%, transparent)",
            padding: "5px 12px",
            borderRadius: "8px",
            border: "1px solid var(--color-line)",
            fontSize: "12px"
          }}>
            <Keyboard size={14} color="var(--color-ink-faint)" />
            <span style={{ color: "var(--color-ink-faint)" }}>Shortcuts:</span>
            <span style={{ color: "var(--color-ok)", fontWeight: 700 }}>[A] / [Enter]</span> Approve
<span style={{ color: "var(--color-bad)", fontWeight: 700 }}>[R] / [Esc]</span> Reject
<span style={{ color: "var(--color-signal)", fontWeight: 700 }}>[S]</span> Scan
          </div>

          <div style={{ display: "flex", gap: "6px" }}>
            <button
              onClick={() => onSimulateCommand("approve")}
              className="btn btn-secondary"
              style={{ padding: "4px 8px", fontSize: "12px", borderColor: "color-mix(in srgb, var(--color-ok) 30%, transparent)", color: "var(--color-ok)" }}
              title="Quick Approve Trade (Key: A)"
            >
              <CheckCircle size={12} /> Approve
            </button>
            <button
              onClick={() => onSimulateCommand("reject")}
              className="btn btn-secondary"
              style={{ padding: "4px 8px", fontSize: "12px", borderColor: "color-mix(in srgb, var(--color-bad) 30%, transparent)", color: "var(--color-bad)" }}
              title="Quick Reject Trade (Key: R)"
            >
              <XCircle size={12} /> Reject
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Voice Active Radar View
  return (
    <div className="glass-panel" style={{ padding: "16px 20px", marginBottom: "20px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "16px" }}>
      {/* Visual radar & status */}
      <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
        <div style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div
            className={isListening ? "radar-active" : ""}
            style={{
              width: "44px",
              height: "44px",
              borderRadius: "50%",
              background: isSpeaking
                ? "var(--color-signal)"
                : isListening
                ? "var(--color-signal)"
                : "color-mix(in srgb, var(--color-ink) 10%, transparent)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transition: "background-color 160ms, border-color 160ms, color 160ms, opacity 160ms"
            }}
          >
            {isSpeaking ? (
              <Volume2 size={22} color="var(--color-ink)" />
            ) : (
              <Mic size={22} color={isListening ? "var(--color-on-signal)" : "var(--color-ink-soft)"} />
            )}
          </div>
        </div>

        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "14px", fontWeight: 700, color: "var(--color-ink)" }}>
              {isSpeaking ? "AI Co-Pilot is Speaking..." : isListening ? "Verbal Trading Radar Active" : "Voice Listening Standby"}
            </span>
            {isSpeaking && (
              <div className="sound-wave">
                <div className="sound-bar" style={{ backgroundColor: "var(--color-signal)" }} />
                <div className="sound-bar" style={{ backgroundColor: "var(--color-signal)" }} />
                <div className="sound-bar" style={{ backgroundColor: "var(--color-signal)" }} />
                <div className="sound-bar" style={{ backgroundColor: "var(--color-signal)" }} />
                <div className="sound-bar" style={{ backgroundColor: "var(--color-signal)" }} />
              </div>
            )}
          </div>
          <div style={{ fontSize: "12px", color: "var(--color-ink-soft)", marginTop: "2px" }}>
            Speak into your mic: <span style={{ color: "var(--color-ok)", fontWeight: 600 }}>"Approve"</span> to confirm trade, or <span style={{ color: "var(--color-bad)", fontWeight: 600 }}>"Reject"</span> to dismiss.
          </div>
        </div>
      </div>

      {/* Transcript feedback box */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        {transcript && (
          <div style={{
            background: "color-mix(in srgb, var(--color-ink) 40%, transparent)",
            border: "1px solid var(--color-edge)",
            borderRadius: "8px",
            padding: "6px 14px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "13px",
            color: "var(--color-signal)"
          }}>
            <MessageSquare size={14} />
            <span>Heard: <em>"{transcript}"</em></span>
          </div>
        )}

        {/* Quick Voice simulation buttons */}
        <div style={{ display: "flex", gap: "6px" }}>
          <button
            onClick={() => onSimulateCommand("approve")}
            className="btn btn-secondary"
            style={{ padding: "5px 10px", fontSize: "12px", borderColor: "color-mix(in srgb, var(--color-ok) 30%, transparent)", color: "var(--color-ok)" }}
            title="Simulate speaking 'Approve'"
          >
            Voice: "Approve"
          </button>
          <button
            onClick={() => onSimulateCommand("reject")}
            className="btn btn-secondary"
            style={{ padding: "5px 10px", fontSize: "12px", borderColor: "color-mix(in srgb, var(--color-bad) 30%, transparent)", color: "var(--color-bad)" }}
            title="Simulate speaking 'Reject'"
          >
            Voice: "Reject"
          </button>
          <button
            onClick={() => onSimulateCommand("scan nifty")}
            className="btn btn-secondary"
            style={{ padding: "5px 10px", fontSize: "12px", borderColor: "color-mix(in srgb, var(--color-signal) 30%, transparent)", color: "var(--color-signal)" }}
            title="Simulate speaking 'Scan Nifty'"
          >
            Voice: "Scan"
          </button>
        </div>
      </div>
    </div>
  );
};
