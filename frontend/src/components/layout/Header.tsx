import React from "react";
import { Settings as SettingsIcon, ShieldCheck, Zap, Bell, Lock, Wallet, RotateCw, Radar } from "lucide-react";
import type { PortfolioSummary, KiteBalance } from "../../types";

interface HeaderProps {
  portfolio: PortfolioSummary | null;
  kiteBalance?: KiteBalance | null;
  isLoadingBalance?: boolean;
  onRefreshBalance?: () => void;
  lastBalanceRefreshTime?: string | null;
  onOpenSettings: () => void;
  onToggleMode?: (mode: "PAPER" | "LIVE") => void;
  notificationPermission: NotificationPermission;
  onRequestNotificationPermission: () => void;
  kiteConnected?: boolean;
  onLogout?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  portfolio,
  kiteBalance,
  isLoadingBalance = false,
  onRefreshBalance,
  lastBalanceRefreshTime,
  onOpenSettings,
  onToggleMode,
  notificationPermission,
  onRequestNotificationPermission,
  kiteConnected,
  onLogout
}) => {
  const isProfit = (portfolio?.total_pnl || 0) >= 0;
  const currentMode = portfolio?.mode || "PAPER";
  const isLiveMode = currentMode === "LIVE";

  const handleModeToggle = () => {
    if (!onToggleMode) return;
    if (!isLiveMode) {
      const confirmLive = window.confirm(
        "⚠️ SWITCH TO LIVE MARKET EXECUTION?\n\nReal intraday orders will be submitted to your Zerodha account using real funds when trades are approved!\n\nAre you sure you want to activate LIVE TRADING?"
      );
      if (confirmLive) {
        onToggleMode("LIVE");
      }
    } else {
      onToggleMode("PAPER");
    }
  };

  return (
    <header className="glass-panel" style={{ padding: "14px 24px", marginBottom: "20px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "14px" }}>
      {/* Brand & Status */}
      <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{
            width: "38px",
            height: "38px",
            borderRadius: "10px",
            background: "linear-gradient(135deg, #00f0ff 0%, #0066ff 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 0 15px rgba(0, 240, 255, 0.4)"
          }}>
            <Zap size={22} color="#001020" />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <h1 style={{ fontSize: "20px", fontWeight: 800, letterSpacing: "-0.5px" }}>KitePulse AI</h1>
              <span style={{
                fontSize: "10px",
                fontWeight: 700,
                background: "rgba(0, 240, 255, 0.15)",
                color: "var(--color-cyan)",
                border: "1px solid var(--border-glow)",
                padding: "2px 6px",
                borderRadius: "4px",
                textTransform: "uppercase",
                display: "inline-flex",
                alignItems: "center",
                gap: "4px"
              }}>
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--color-bull)" }}></span>
                Quant Engine v2
              </span>
            </div>
            <div style={{ fontSize: "12px", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "6px" }}>
              <span>Zerodha Kite</span>
              <span>•</span>
              <span style={{ color: "#a855f7" }}>A+ Setup Hunter</span>
            </div>
          </div>
        </div>

        {/* 1-Click Interactive Trading Mode Toggle */}
        <button
          onClick={handleModeToggle}
          className="btn"
          style={{
            padding: "6px 14px",
            borderRadius: "20px",
            background: isLiveMode ? "rgba(0, 230, 153, 0.18)" : "rgba(0, 240, 255, 0.12)",
            border: `1px solid ${isLiveMode ? "rgba(0, 230, 153, 0.5)" : "rgba(0, 240, 255, 0.4)"}`,
            display: "flex",
            alignItems: "center",
            gap: "7px",
            fontSize: "12px",
            fontWeight: 800,
            cursor: "pointer",
            color: isLiveMode ? "var(--color-bull)" : "var(--color-cyan)",
            boxShadow: isLiveMode ? "0 0 12px rgba(0, 230, 153, 0.25)" : "none",
            transition: "all 0.2s ease"
          }}
          title={isLiveMode ? "⚡ LIVE EXECUTION ACTIVE: Real orders sent to Zerodha. Click to switch to Sandbox simulation." : "🧪 SANDBOX MODE ACTIVE: Orders simulated safely. Click to switch to Live execution."}
        >
          <ShieldCheck size={15} />
          <span>{isLiveMode ? "⚡ LIVE TRADING (REAL ORDERS)" : "🧪 SANDBOX (PAPER SIMULATION)"}</span>
          <span style={{
            fontSize: "10px",
            padding: "2px 6px",
            borderRadius: "10px",
            background: isLiveMode ? "rgba(0, 230, 153, 0.25)" : "rgba(0, 240, 255, 0.2)",
            marginLeft: "2px"
          }}>
            Click to switch
          </span>
        </button>

        {/* Autonomous Opportunity Scanner Status Indicator */}
        <div style={{
          padding: "5px 12px",
          borderRadius: "12px",
          background: "rgba(0, 230, 153, 0.08)",
          border: "1px solid rgba(0, 230, 153, 0.3)",
          display: "flex",
          alignItems: "center",
          gap: "7px",
          fontSize: "12px",
          fontWeight: 600,
          color: "var(--color-bull)"
        }}>
          <Radar size={14} style={{ animation: "spin 4s linear infinite" }} />
          <span>Auto-Scanner Active (A+ Filter)</span>
        </div>

        {/* Broker Feed Status Indicator */}
        <div style={{
          padding: "5px 10px",
          borderRadius: "12px",
          background: "rgba(255, 255, 255, 0.04)",
          border: "1px solid var(--border-color)",
          display: "flex",
          alignItems: "center",
          gap: "6px",
          fontSize: "11px",
          color: kiteConnected ? "var(--text-muted)" : "#ffb300"
        }}>
          <span style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: kiteConnected ? "var(--color-bull)" : "#ffb300",
            boxShadow: kiteConnected ? "0 0 6px var(--color-bull)" : "none"
          }} />
          <span>{kiteConnected ? "Kite Feed Connected" : "Kite Disconnected"}</span>
        </div>
      </div>

      {/* Stats & Actions */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
        {/* Desktop Notification Request Button */}
        {notificationPermission !== "granted" ? (
          <button
            onClick={onRequestNotificationPermission}
            className="btn btn-primary"
            style={{ padding: "6px 12px", fontSize: "12px" }}
            title="Enable Windows Desktop Notifications for trade alerts"
          >
            <Bell size={14} />
            <span>Enable Desktop Alerts</span>
          </button>
        ) : (
          <div
            style={{
              padding: "6px 10px",
              borderRadius: "8px",
              background: "rgba(0, 230, 153, 0.1)",
              border: "1px solid rgba(0, 230, 153, 0.25)",
              color: "var(--color-bull)",
              fontSize: "11px",
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: "4px"
            }}
            title="Desktop Notifications Active"
          >
            <Bell size={13} />
            <span>Alerts Active</span>
          </div>
        )}

        {/* Kite Account Balance & 1-Click Refresh */}
        <div
          className="glass-panel"
          style={{
            padding: "6px 14px",
            display: "flex",
            alignItems: "center",
            gap: "12px",
            borderRadius: "10px",
            background: "rgba(10, 16, 29, 0.7)",
            border: "1px solid rgba(0, 240, 255, 0.25)",
            boxShadow: "0 0 15px rgba(0, 240, 255, 0.06)"
          }}
        >
          <div
            style={{
              width: "32px",
              height: "32px",
              borderRadius: "8px",
              background: kiteConnected ? "rgba(0, 240, 255, 0.12)" : "rgba(255, 179, 0, 0.12)",
              border: `1px solid ${kiteConnected ? "rgba(0, 240, 255, 0.3)" : "rgba(255, 179, 0, 0.3)"}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: kiteConnected ? "var(--color-cyan)" : "#ffb300"
            }}
            title={kiteConnected ? "Zerodha Kite Connected" : "Kite Disconnected"}
          >
            <Wallet size={16} />
          </div>

          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span style={{ fontSize: "10px", color: "var(--text-dim)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.4px" }}>
                Kite Balance
              </span>
              {kiteBalance?.equity && (
                <span style={{
                  fontSize: "9px",
                  padding: "1px 5px",
                  borderRadius: "4px",
                  background: "rgba(0, 230, 153, 0.15)",
                  color: "var(--color-bull)",
                  fontWeight: 600
                }}>
                  Live
                </span>
              )}
            </div>

            {kiteConnected && kiteBalance?.equity ? (
              <div style={{ display: "flex", alignItems: "baseline", gap: "5px" }}>
                <div
                  className="font-mono"
                  style={{
                    fontSize: "15px",
                    fontWeight: 700,
                    color: "var(--color-cyan)",
                    textShadow: "0 0 10px rgba(0, 240, 255, 0.3)"
                  }}
                  title={`Available Cash: ₹${kiteBalance.equity.available_cash.toLocaleString('en-IN', { minimumFractionDigits: 2 })} | Total Net Margin: ₹${kiteBalance.equity.net.toLocaleString('en-IN', { minimumFractionDigits: 2 })} | Utilised: ₹${kiteBalance.equity.utilised.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
                >
                  ₹{kiteBalance.equity.available_cash.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <span style={{ fontSize: "10px", color: "var(--text-dim)" }}>
                  rem.
                </span>
              </div>
            ) : kiteConnected && isLoadingBalance ? (
              <div style={{ fontSize: "12px", color: "var(--text-muted)", fontStyle: "italic" }}>
                Fetching...
              </div>
            ) : kiteConnected ? (
              <div
                onClick={onRefreshBalance}
                style={{ fontSize: "12px", color: "var(--color-cyan)", cursor: "pointer", fontWeight: 600 }}
              >
                Click Refresh
              </div>
            ) : (
              <div
                onClick={onOpenSettings}
                style={{ fontSize: "12px", color: "#ffb300", cursor: "pointer", fontWeight: 600 }}
                title="Click to configure credentials & login"
              >
                Not Connected
              </div>
            )}
          </div>

          {/* 1-Click Refresh Button */}
          {onRefreshBalance && (
            <button
              onClick={onRefreshBalance}
              disabled={isLoadingBalance}
              className="btn btn-secondary"
              style={{
                padding: "6px 8px",
                borderRadius: "6px",
                cursor: isLoadingBalance ? "not-allowed" : "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid var(--border-color)",
                color: "var(--text-main)",
                marginLeft: "2px"
              }}
              title={
                lastBalanceRefreshTime
                  ? `Refresh Kite Balance (Last fetched: ${lastBalanceRefreshTime})`
                  : "Refresh remaining balance from Zerodha Kite"
              }
            >
              <RotateCw
                size={14}
                style={{
                  animation: isLoadingBalance ? "spin 1s linear infinite" : "none",
                  color: isLoadingBalance ? "var(--color-cyan)" : "inherit"
                }}
              />
            </button>
          )}
        </div>

        {/* P&L Tracker */}
        <div className="glass-panel" style={{ padding: "6px 14px", display: "flex", alignItems: "center", gap: "12px", borderRadius: "10px" }}>
          <div>
            <div style={{ fontSize: "10px", color: "var(--text-dim)", textTransform: "uppercase" }}>Total P&L</div>
            <div className="font-mono" style={{
              fontSize: "15px",
              fontWeight: 700,
              color: isProfit ? "var(--color-bull)" : "var(--color-bear)",
              textShadow: isProfit ? "0 0 10px var(--color-bull-glow)" : "0 0 10px var(--color-bear-glow)"
            }}>
              {isProfit ? "+" : ""}₹{portfolio?.total_pnl.toFixed(2) || "0.00"}
            </div>
          </div>
          <div style={{ width: "1px", height: "20px", background: "var(--border-color)" }} />
          <div>
            <div style={{ fontSize: "10px", color: "var(--text-dim)", textTransform: "uppercase" }}>Lot Size</div>
            <div className="font-mono" style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-main)" }}>
              1 Lot (Safe)
            </div>
          </div>
        </div>

        {/* Settings Button */}
        <button
          onClick={onOpenSettings}
          className="btn btn-secondary"
          title="Configure Zerodha Kite, the AI provider, and notification webhooks"
          style={{ padding: "7px 12px" }}
        >
          <SettingsIcon size={15} />
          <span style={{ fontSize: "12px" }}>Settings</span>
        </button>

        {/* Lock Vault / Logout Button */}
        {onLogout && (
          <button
            onClick={onLogout}
            className="btn btn-secondary"
            title="Lock Security Vault & Logout"
            style={{
              padding: "7px 12px",
              borderColor: "rgba(255, 59, 48, 0.3)",
              color: "#ff8080"
            }}
          >
            <Lock size={14} color="#ff8080" />
            <span style={{ fontSize: "12px" }}>Lock Vault</span>
          </button>
        )}
      </div>
    </header>
  );
};
