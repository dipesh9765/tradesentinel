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
        "Switch to live trading?\n\nReal intraday orders will be submitted to your Zerodha account using real funds when trades are approved!\n\nAre you sure you want to activate LIVE TRADING?"
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
            background: "var(--color-signal)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}>
            <Zap size={22} color="var(--color-on-signal)" />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <h1 style={{ fontSize: "20px", fontWeight: 800, }}>TradeSentinel</h1>
              <span style={{
                fontSize: "12px",
                fontWeight: 700,
                background: "color-mix(in srgb, var(--color-signal) 15%, transparent)",
                color: "var(--color-signal)",
                border: "1px solid var(--color-edge)",
                padding: "2px 6px",
                borderRadius: "4px",
                display: "inline-flex",
                alignItems: "center",
                gap: "4px"
              }}>
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--color-ok)" }}></span>
                Quant Engine v2
              </span>
            </div>
            <div style={{ fontSize: "12px", color: "var(--color-ink-soft)", display: "flex", alignItems: "center", gap: "6px" }}>
              <span>Zerodha Kite</span>
<span style={{ color: "var(--color-signal)" }}>A+ Setup Hunter</span>
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
            background: isLiveMode ? "color-mix(in srgb, var(--color-ok) 18%, transparent)" : "color-mix(in srgb, var(--color-signal) 12%, transparent)",
            border: `1px solid ${isLiveMode ? "color-mix(in srgb, var(--color-ok) 50%, transparent)" : "color-mix(in srgb, var(--color-signal) 40%, transparent)"}`,
            display: "flex",
            alignItems: "center",
            gap: "7px",
            fontSize: "12px",
            fontWeight: 800,
            cursor: "pointer",
            color: isLiveMode ? "var(--color-ok)" : "var(--color-signal)",
            transition: "background-color 160ms, border-color 160ms, color 160ms, opacity 160ms"
          }}
          title={isLiveMode ? "Live trading is on: real orders sent to Zerodha. Click to switch to Sandbox simulation." : "Sandbox is on: orders simulated safely. Click to switch to Live execution."}
        >
          <ShieldCheck size={15} />
          <span>{isLiveMode ? "Live trading (real orders)" : "Sandbox (paper trades)"}</span>
          <span style={{
            fontSize: "12px",
            padding: "2px 6px",
            borderRadius: "10px",
            background: isLiveMode ? "color-mix(in srgb, var(--color-ok) 25%, transparent)" : "color-mix(in srgb, var(--color-signal) 20%, transparent)",
            marginLeft: "2px"
          }}>
            Click to switch
          </span>
        </button>

        {/* Autonomous Opportunity Scanner Status Indicator */}
        <div style={{
          padding: "5px 12px",
          borderRadius: "12px",
          background: "color-mix(in srgb, var(--color-ok) 8%, transparent)",
          border: "1px solid color-mix(in srgb, var(--color-ok) 30%, transparent)",
          display: "flex",
          alignItems: "center",
          gap: "7px",
          fontSize: "12px",
          fontWeight: 600,
          color: "var(--color-ok)"
        }}>
          <Radar size={14} style={{ animation: "spin 4s linear infinite" }} />
          <span>Auto-Scanner Active (A+ Filter)</span>
        </div>

        {/* Broker Feed Status Indicator */}
        <div style={{
          padding: "5px 10px",
          borderRadius: "12px",
          background: "color-mix(in srgb, var(--color-ink) 4%, transparent)",
          border: "1px solid var(--color-line)",
          display: "flex",
          alignItems: "center",
          gap: "6px",
          fontSize: "12px",
          color: kiteConnected ? "var(--color-ink-soft)" : "var(--color-warn)"
        }}>
          <span style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: kiteConnected ? "var(--color-ok)" : "var(--color-warn)",
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
              background: "color-mix(in srgb, var(--color-ok) 10%, transparent)",
              border: "1px solid color-mix(in srgb, var(--color-ok) 25%, transparent)",
              color: "var(--color-ok)",
              fontSize: "12px",
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
            background: "color-mix(in srgb, var(--color-paper) 70%, transparent)",
            border: "1px solid color-mix(in srgb, var(--color-signal) 25%, transparent)",
          }}
        >
          <div
            style={{
              width: "32px",
              height: "32px",
              borderRadius: "8px",
              background: kiteConnected ? "color-mix(in srgb, var(--color-signal) 12%, transparent)" : "color-mix(in srgb, var(--color-warn) 12%, transparent)",
              border: `1px solid ${kiteConnected ? "color-mix(in srgb, var(--color-signal) 30%, transparent)" : "color-mix(in srgb, var(--color-warn) 30%, transparent)"}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: kiteConnected ? "var(--color-signal)" : "var(--color-warn)"
            }}
            title={kiteConnected ? "Zerodha Kite Connected" : "Kite Disconnected"}
          >
            <Wallet size={16} />
          </div>

          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span style={{ fontSize: "12px", color: "var(--color-ink-faint)", fontWeight: 700, }}>
                Kite Balance
              </span>
              {kiteBalance?.equity && (
                <span style={{
                  fontSize: "12px",
                  padding: "1px 5px",
                  borderRadius: "4px",
                  background: "color-mix(in srgb, var(--color-ok) 15%, transparent)",
                  color: "var(--color-ok)",
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
                    color: "var(--color-signal)",
                    textShadow: "0 0 10px color-mix(in srgb, var(--color-signal) 30%, transparent)"
                  }}
                  title={`Available Cash: ₹${kiteBalance.equity.available_cash.toLocaleString('en-IN', { minimumFractionDigits: 2 })} | Total Net Margin: ₹${kiteBalance.equity.net.toLocaleString('en-IN', { minimumFractionDigits: 2 })} | Utilised: ₹${kiteBalance.equity.utilised.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`}
                >
                  ₹{kiteBalance.equity.available_cash.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <span style={{ fontSize: "12px", color: "var(--color-ink-faint)" }}>
                  rem.
                </span>
              </div>
            ) : kiteConnected && isLoadingBalance ? (
              <div style={{ fontSize: "12px", color: "var(--color-ink-soft)", fontStyle: "italic" }}>
                Fetching...
              </div>
            ) : kiteConnected ? (
              <div
                onClick={onRefreshBalance}
                style={{ fontSize: "12px", color: "var(--color-signal)", cursor: "pointer", fontWeight: 600 }}
              >
                Click Refresh
              </div>
            ) : (
              <div
                onClick={onOpenSettings}
                style={{ fontSize: "12px", color: "var(--color-warn)", cursor: "pointer", fontWeight: 600 }}
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
                background: "color-mix(in srgb, var(--color-ink) 5%, transparent)",
                border: "1px solid var(--color-line)",
                color: "var(--color-ink)",
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
                  color: isLoadingBalance ? "var(--color-signal)" : "inherit"
                }}
              />
            </button>
          )}
        </div>

        {/* P&L Tracker */}
        <div className="glass-panel" style={{ padding: "6px 14px", display: "flex", alignItems: "center", gap: "12px", borderRadius: "10px" }}>
          <div>
            <div style={{ fontSize: "12px", color: "var(--color-ink-faint)", }}>Total P&L</div>
            <div className="font-mono" style={{
              fontSize: "15px",
              fontWeight: 700,
              color: isProfit ? "var(--color-ok)" : "var(--color-bad)",
              textShadow: isProfit ? "0 0 10px transparent" : "0 0 10px transparent"
            }}>
              {isProfit ? "+" : ""}₹{portfolio?.total_pnl.toFixed(2) || "0.00"}
            </div>
          </div>
          <div style={{ width: "1px", height: "20px", background: "var(--color-line)" }} />
          <div>
            <div style={{ fontSize: "12px", color: "var(--color-ink-faint)", }}>Lot Size</div>
            <div className="font-mono" style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-ink)" }}>
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
              borderColor: "color-mix(in srgb, var(--color-bad) 30%, transparent)",
              color: "var(--color-bad)"
            }}
          >
            <Lock size={14} color="var(--color-bad)" />
            <span style={{ fontSize: "12px" }}>Lock Vault</span>
          </button>
        )}
      </div>
    </header>
  );
};
