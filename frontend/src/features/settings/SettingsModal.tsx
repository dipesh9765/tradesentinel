import React, { useState, useEffect } from "react";
import { X, Key, ExternalLink, Check, Bell, Send, Eye, EyeOff, ShieldCheck, Lock, CheckCircle2, AlertCircle, Smartphone } from "lucide-react";
import { fetchSettingsApi, generateKiteSessionApi } from "../../services/api";
import { AIProviderSettings } from "./AIProviderSettings";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (settings: {
    kite_api_key?: string;
    kite_api_secret?: string;
    kite_access_token?: string;
    gemini_api_key?: string;
    trading_mode?: string;
    telegram_bot_token?: string;
    telegram_chat_id?: string;
    discord_webhook_url?: string;
    slack_webhook_url?: string;
  }) => Promise<void>;
  currentMode?: "PAPER" | "LIVE" | string;
  onOpenKiteLogin: () => void;
  onTestNotification: () => Promise<void>;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  onSave,
  currentMode = "PAPER",
  onOpenKiteLogin,
  onTestNotification
}) => {
  const [kiteKey, setKiteKey] = useState("");
  const [kiteSecret, setKiteSecret] = useState("");
  const [kiteToken, setKiteToken] = useState("");
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [discordWebhook, setDiscordWebhook] = useState("");
  const [slackWebhook, setSlackWebhook] = useState("");
  const [mode, setMode] = useState<"PAPER" | "LIVE">((currentMode as "PAPER" | "LIVE") || "PAPER");
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [testingNotification, setTestingNotification] = useState(false);
  const [configuredStatus, setConfiguredStatus] = useState<any>(null);

  // Manual OAuth Redirect / Request Token helper state
  const [pastedRedirectInput, setPastedRedirectInput] = useState("");
  const [isActivatingSession, setIsActivatingSession] = useState(false);
  const [sessionSuccessMessage, setSessionSuccessMessage] = useState<string | null>(null);
  const [sessionErrorMessage, setSessionErrorMessage] = useState<string | null>(null);

  // Field visibility toggles
  const [showKiteSecret, setShowKiteSecret] = useState(false);
  const [showKiteToken, setShowKiteToken] = useState(false);
  const [showTelegramToken, setShowTelegramToken] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetchSettingsApi()
        .then((data) => {
          setConfiguredStatus(data);
          if (data.trading_mode) setMode(data.trading_mode);
          if (data.telegram_bot_token) setTelegramToken(data.telegram_bot_token);
          if (data.telegram_chat_id) setTelegramChatId(data.telegram_chat_id);
          if (data.discord_webhook_url) setDiscordWebhook(data.discord_webhook_url);
          if (data.slack_webhook_url) setSlackWebhook(data.slack_webhook_url);
        })
        .catch((e) => console.warn("Failed to load settings preview:", e));
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave({
        kite_api_key: kiteKey || undefined,
        kite_api_secret: kiteSecret || undefined,
        kite_access_token: kiteToken || undefined,
        trading_mode: mode,
        telegram_bot_token: telegramToken || undefined,
        telegram_chat_id: telegramChatId || undefined,
        discord_webhook_url: discordWebhook || undefined,
        slack_webhook_url: slackWebhook || undefined
      });
      setSavedSuccess(true);
      setTimeout(() => {
        setSavedSuccess(false);
        onClose();
      }, 1200);
    } catch (err) {
      alert("Failed to save settings: " + err);
    } finally {
      setSaving(false);
    }
  };

  const handleActivateSessionFromRedirect = async () => {
    if (!pastedRedirectInput.trim()) {
      setSessionErrorMessage("Please paste the redirect URL or request_token first.");
      return;
    }
    setIsActivatingSession(true);
    setSessionErrorMessage(null);
    setSessionSuccessMessage(null);
    try {
      await generateKiteSessionApi(pastedRedirectInput.trim());
      setSessionSuccessMessage("✅ Zerodha Kite daily session authenticated successfully!");
      setPastedRedirectInput("");
      const updated = await fetchSettingsApi();
      setConfiguredStatus(updated);
    } catch (e: any) {
      setSessionErrorMessage(e.message || "Failed to generate session. Please check your Kite API Secret.");
    } finally {
      setIsActivatingSession(false);
    }
  };

  const handleSendTest = async () => {
    setTestingNotification(true);
    try {
      await onTestNotification();
    } catch (e: any) {
      alert("Test alert error: " + e.message);
    } finally {
      setTestingNotification(false);
    }
  };

  return (
    <div style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: "rgba(0, 0, 0, 0.82)",
      backdropFilter: "blur(10px)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 9999,
      padding: "16px"
    }}>
      <div className="glass-panel" style={{
        width: "100%",
        maxWidth: "620px",
        maxHeight: "92vh",
        overflowY: "auto",
        padding: "26px",
        borderRadius: "16px",
        background: "#0c111d",
        border: "1px solid rgba(0, 240, 255, 0.25)",
        boxShadow: "0 12px 40px rgba(0, 0, 0, 0.8), 0 0 25px rgba(0, 240, 255, 0.15)"
      }}>
        {/* Modal Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "22px", paddingBottom: "14px", borderBottom: "1px solid rgba(255, 255, 255, 0.1)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{ background: "rgba(0, 240, 255, 0.15)", padding: "8px", borderRadius: "8px", display: "flex" }}>
              <Key size={20} color="var(--color-cyan)" />
            </div>
            <div>
              <h2 style={{ fontSize: "19px", fontWeight: 800, color: "#ffffff", letterSpacing: "0.3px" }}>Trading & API Configuration</h2>
              <p style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "2px" }}>Set your Zerodha Kite keys, AI models, and notification alerts</p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              background: "rgba(255, 255, 255, 0.05)",
              border: "1px solid rgba(255, 255, 255, 0.1)",
              borderRadius: "8px",
              color: "#cbd5e1",
              cursor: "pointer",
              padding: "6px",
              display: "flex",
              alignItems: "center"
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* SQLite Encrypted Vault Notice */}
        <div style={{
          background: "rgba(0, 240, 255, 0.08)",
          border: "1px solid rgba(0, 240, 255, 0.25)",
          borderRadius: "10px",
          padding: "12px 14px",
          display: "flex",
          alignItems: "center",
          gap: "10px",
          marginBottom: "20px"
        }}>
          <Lock size={18} color="#00f0ff" style={{ flexShrink: 0 }} />
          <div style={{ fontSize: "12px", color: "#cbd5e1", lineHeight: "1.4" }}>
            <strong style={{ color: "#00f0ff" }}>Encrypted Local Database Vault:</strong> All API keys and secrets entered here are encrypted with AES-256 Fernet using your Master Password. Raw keys are never stored in plain text or exposed to unauthorized parties.
          </div>
        </div>

        <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "22px" }}>
          {/* Section 1: Execution Engine Selection */}
          <div className="form-group">
            <div className="form-label">
              <span>Trading Execution Engine</span>
              <span className="form-label-badge" style={{ color: mode === "LIVE" ? "var(--color-bull)" : "var(--color-cyan)" }}>
                Active: {mode}
              </span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <div
                onClick={() => setMode("PAPER")}
                style={{
                  padding: "14px",
                  borderRadius: "10px",
                  cursor: "pointer",
                  border: `2px solid ${mode === "PAPER" ? "var(--color-cyan)" : "rgba(255, 255, 255, 0.1)"}`,
                  background: mode === "PAPER" ? "rgba(0, 240, 255, 0.12)" : "#101625",
                  transition: "all 0.2s ease"
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontWeight: 700, fontSize: "14.5px", color: mode === "PAPER" ? "var(--color-cyan)" : "#ffffff" }}>
                    Paper Sandbox
                  </span>
                  {mode === "PAPER" && <ShieldCheck size={16} color="var(--color-cyan)" />}
                </div>
                <div style={{ fontSize: "12px", color: "#94a3b8", marginTop: "4px" }}>
                  Virtual simulation (Lot locked to 1)
                </div>
              </div>

              <div
                onClick={() => setMode("LIVE")}
                style={{
                  padding: "14px",
                  borderRadius: "10px",
                  cursor: "pointer",
                  border: `2px solid ${mode === "LIVE" ? "var(--color-bull)" : "rgba(255, 255, 255, 0.1)"}`,
                  background: mode === "LIVE" ? "rgba(0, 230, 153, 0.12)" : "#101625",
                  transition: "all 0.2s ease"
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontWeight: 700, fontSize: "14.5px", color: mode === "LIVE" ? "var(--color-bull)" : "#ffffff" }}>
                    Zerodha Kite Live
                  </span>
                  {mode === "LIVE" && <ShieldCheck size={16} color="var(--color-bull)" />}
                </div>
                <div style={{ fontSize: "12px", color: "#94a3b8", marginTop: "4px" }}>
                  Real MIS Intraday Orders (Kite API)
                </div>
              </div>
            </div>
          </div>

          {/* Section 2: Zerodha Kite Connect Credentials */}
          <div style={{
            background: "#0f1523",
            padding: "16px",
            borderRadius: "12px",
            border: "1px solid rgba(255, 255, 255, 0.1)",
            display: "flex",
            flexDirection: "column",
            gap: "14px"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ fontSize: "13px", fontWeight: 700, color: "#ffffff", display: "flex", alignItems: "center", gap: "6px" }}>
                  Zerodha Kite Connect Credentials
                </span>
                <span className="form-hint">From developers.kite.trade under your created App</span>
              </div>
              <button
                type="button"
                onClick={onOpenKiteLogin}
                className="btn btn-secondary"
                style={{ padding: "6px 10px", fontSize: "12px", display: "flex", alignItems: "center", gap: "5px" }}
              >
                <ExternalLink size={13} /> Kite OAuth Login
              </button>
            </div>

            {/* Kite API Key */}
            <div className="form-group">
              <label className="form-label" htmlFor="kite-api-key">
                <span>Kite API Key</span>
                <span className="form-label-badge">From App Details</span>
              </label>
              <div className="form-input-container">
                <input
                  id="kite-api-key"
                  type="text"
                  placeholder={configuredStatus?.kite_api_key_preview || "e.g. z9k8p7q6m5n4b3v2"}
                  value={kiteKey}
                  onChange={(e) => setKiteKey(e.target.value)}
                  className="form-input"
                  autoComplete="off"
                />
              </div>
            </div>

            {/* Kite API Secret */}
            <div className="form-group">
              <label className="form-label" htmlFor="kite-api-secret">
                <span>Kite API Secret</span>
                <span className="form-label-badge">Confidential</span>
              </label>
              <div className="form-input-container">
                <input
                  id="kite-api-secret"
                  type={showKiteSecret ? "text" : "password"}
                  placeholder={configuredStatus?.kite_api_secret_preview || "e.g. 1a2b3c4d5e6f7g8h9i0j..."}
                  value={kiteSecret}
                  onChange={(e) => setKiteSecret(e.target.value)}
                  className="form-input"
                  style={{ paddingRight: "40px" }}
                  autoComplete="off"
                />
                <button
                  type="button"
                  onClick={() => setShowKiteSecret(!showKiteSecret)}
                  className="form-input-action"
                  title={showKiteSecret ? "Hide secret" : "Show secret"}
                >
                  {showKiteSecret ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Daily Access Token */}
            <div className="form-group">
              <label className="form-label" htmlFor="kite-access-token">
                <span>Daily Access Token (Optional)</span>
                <span style={{ fontSize: "11px", color: "#94a3b8" }}>Auto-generated by Kite Login</span>
              </label>
              <div className="form-input-container">
                <input
                  id="kite-access-token"
                  type={showKiteToken ? "text" : "password"}
                  placeholder={configuredStatus?.kite_access_token_preview || "Auto-filled after clicking Kite OAuth Login"}
                  value={kiteToken}
                  onChange={(e) => setKiteToken(e.target.value)}
                  className="form-input"
                  style={{ paddingRight: "40px" }}
                  autoComplete="off"
                />
                <button
                  type="button"
                  onClick={() => setShowKiteToken(!showKiteToken)}
                  className="form-input-action"
                  title={showKiteToken ? "Hide token" : "Show token"}
                >
                  {showKiteToken ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <span className="form-hint">
                Tip: Click <strong>Kite OAuth Login</strong> above to automatically generate this token each morning with 1 click.
              </span>
            </div>

            {/* Mobile & Remote Kite Session Activator */}
            <div style={{
              background: "rgba(0, 240, 255, 0.04)",
              border: "1px dashed rgba(0, 240, 255, 0.3)",
              borderRadius: "8px",
              padding: "12px",
              marginTop: "4px"
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
                <Smartphone size={16} color="var(--color-cyan)" />
                <span style={{ fontSize: "12px", fontWeight: 700, color: "#ffffff" }}>
                  Mobile & Remote OAuth Token Helper
                </span>
              </div>
              <p style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "8px", lineHeight: "1.4" }}>
                If Zerodha redirects to a broken <em>localhost</em> URL on your phone, copy the entire URL or <code>request_token</code> from your mobile browser bar and paste it below:
              </p>
              
              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                <input
                  type="text"
                  placeholder="Paste URL (e.g. http://localhost:5173/?request_token=...)"
                  value={pastedRedirectInput}
                  onChange={(e) => setPastedRedirectInput(e.target.value)}
                  className="form-input"
                  style={{ flex: "1 1 200px", fontSize: "12px", padding: "8px 10px" }}
                />
                <button
                  type="button"
                  onClick={handleActivateSessionFromRedirect}
                  disabled={isActivatingSession}
                  className="btn btn-primary"
                  style={{ padding: "8px 14px", fontSize: "12px", whiteSpace: "nowrap" }}
                >
                  {isActivatingSession ? "Activating..." : "Activate Session"}
                </button>
              </div>

              {sessionSuccessMessage && (
                <div style={{ marginTop: "8px", fontSize: "11.5px", color: "var(--color-bull)", display: "flex", alignItems: "center", gap: "6px" }}>
                  <CheckCircle2 size={14} />
                  <span>{sessionSuccessMessage}</span>
                </div>
              )}
              {sessionErrorMessage && (
                <div style={{ marginTop: "8px", fontSize: "11.5px", color: "var(--color-bear)", display: "flex", alignItems: "center", gap: "6px" }}>
                  <AlertCircle size={14} />
                  <span>{sessionErrorMessage}</span>
                </div>
              )}
            </div>
          </div>

          {/* Section 3: AI Provider & Model */}
          <AIProviderSettings />

          {/* Section 4: Office App Notifications */}
          <div style={{
            background: "#0f1523",
            padding: "16px",
            borderRadius: "12px",
            border: "1px solid rgba(255, 255, 255, 0.1)",
            display: "flex",
            flexDirection: "column",
            gap: "12px"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ fontSize: "13px", fontWeight: 700, color: "#ffffff", display: "flex", alignItems: "center", gap: "6px" }}>
                  <Bell size={15} color="var(--color-cyan)" /> Office App Notifications
                </span>
                <span className="form-hint">Sends silent alerts to your phone while at work</span>
              </div>
              <button
                type="button"
                onClick={handleSendTest}
                disabled={testingNotification}
                className="btn btn-secondary"
                style={{ padding: "5px 12px", fontSize: "11.5px", display: "flex", alignItems: "center", gap: "5px" }}
              >
                <Send size={12} /> {testingNotification ? "Sending..." : "Test Alerts"}
              </button>
            </div>

            {/* Telegram Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: "10px" }}>
              <div className="form-group">
                <label className="form-label" htmlFor="telegram-token">
                  <span>Telegram Bot Token</span>
                </label>
                <div className="form-input-container">
                  <input
                    id="telegram-token"
                    type={showTelegramToken ? "text" : "password"}
                    placeholder="123456789:ABCdef..."
                    value={telegramToken}
                    onChange={(e) => setTelegramToken(e.target.value)}
                    className="form-input"
                    style={{ paddingRight: "38px" }}
                    autoComplete="off"
                  />
                  <button
                    type="button"
                    onClick={() => setShowTelegramToken(!showTelegramToken)}
                    className="form-input-action"
                    title={showTelegramToken ? "Hide token" : "Show token"}
                  >
                    {showTelegramToken ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="telegram-chat-id">
                  <span>Telegram Chat ID</span>
                </label>
                <input
                  id="telegram-chat-id"
                  type="text"
                  placeholder="e.g. 987654321"
                  value={telegramChatId}
                  onChange={(e) => setTelegramChatId(e.target.value)}
                  className="form-input"
                  autoComplete="off"
                />
              </div>
            </div>

            {/* Discord Webhook */}
            <div className="form-group">
              <label className="form-label" htmlFor="discord-webhook">
                <span>Discord Webhook URL</span>
              </label>
              <input
                id="discord-webhook"
                type="text"
                placeholder="https://discord.com/api/webhooks/..."
                value={discordWebhook}
                onChange={(e) => setDiscordWebhook(e.target.value)}
                className="form-input"
                autoComplete="off"
              />
            </div>

            {/* Slack Webhook */}
            <div className="form-group">
              <label className="form-label" htmlFor="slack-webhook">
                <span>Slack Webhook URL</span>
              </label>
              <input
                id="slack-webhook"
                type="text"
                placeholder="https://hooks.slack.com/services/..."
                value={slackWebhook}
                onChange={(e) => setSlackWebhook(e.target.value)}
                className="form-input"
                autoComplete="off"
              />
            </div>
          </div>

          {/* Action Buttons */}
          <div style={{ display: "flex", gap: "12px", marginTop: "4px" }}>
            <button
              type="submit"
              disabled={saving}
              className="btn btn-primary"
              style={{ flex: 1, padding: "13px", fontSize: "14.5px", fontWeight: 700 }}
            >
              {savedSuccess ? (
                <>
                  <Check size={18} /> Configuration Saved!
                </>
              ) : (
                saving ? "Saving Configuration..." : "Save Settings"
              )}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="btn btn-secondary"
              style={{ padding: "13px 22px", fontSize: "14px" }}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

