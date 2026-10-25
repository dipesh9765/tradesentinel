import React, { useState } from "react";
import { Shield, Lock, Key, AlertCircle, CheckCircle2, Eye, EyeOff } from "lucide-react";
import { setupMasterPasswordApi, loginMasterPasswordApi } from "../../services/api";

interface AuthGatekeeperProps {
  isInitialized: boolean;
  onAuthenticated: () => void;
}

export const AuthGatekeeper: React.FC<AuthGatekeeperProps> = ({
  isInitialized,
  onAuthenticated
}) => {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSetup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password.length < 6) {
      setError("Master password must be at least 6 characters long.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match. Please re-enter carefully.");
      return;
    }

    setLoading(true);
    try {
      await setupMasterPasswordApi(password);
      onAuthenticated();
    } catch (err: any) {
      setError(err.message || "Failed to initialize master password.");
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!password) {
      setError("Please enter your master password.");
      return;
    }

    setLoading(true);
    try {
      await loginMasterPasswordApi(password);
      onAuthenticated();
    } catch (err: any) {
      setError(err.message || "Invalid master password. Access denied.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "radial-gradient(circle at 50% 20%, #0d1527 0%, #060911 100%)",
        padding: "20px",
        fontFamily: "'Inter', sans-serif"
      }}
    >
      <div
        className="glass-panel"
        style={{
          width: "100%",
          maxWidth: "460px",
          padding: "36px 32px",
          borderRadius: "20px",
          background: "rgba(13, 19, 33, 0.85)",
          border: "1px solid rgba(0, 240, 255, 0.25)",
          boxShadow: "0 20px 50px rgba(0, 0, 0, 0.8), 0 0 35px rgba(0, 240, 255, 0.12)",
          backdropFilter: "blur(16px)"
        }}
      >
        {/* Shield Icon Header */}
        <div style={{ textAlign: "center", marginBottom: "26px" }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "64px",
              height: "64px",
              borderRadius: "50%",
              background: "rgba(0, 240, 255, 0.12)",
              border: "1px solid rgba(0, 240, 255, 0.35)",
              boxShadow: "0 0 20px rgba(0, 240, 255, 0.25)",
              marginBottom: "16px"
            }}
          >
            {isInitialized ? (
              <Lock size={30} color="var(--color-cyan, #00f0ff)" />
            ) : (
              <Shield size={30} color="var(--color-cyan, #00f0ff)" />
            )}
          </div>

          <h1 style={{ fontSize: "24px", fontWeight: 800, color: "#ffffff", letterSpacing: "0.5px" }}>
            {isInitialized ? "TradeSentinel Security Vault" : "Create Master Security Key"}
          </h1>
          <p style={{ fontSize: "13.5px", color: "#94a3b8", marginTop: "6px", lineHeight: "1.5" }}>
            {isInitialized
              ? "This terminal is locked. Enter your Master Password to decrypt your Zerodha Kite and AI credentials."
              : "Set your Master Password to encrypt all credentials in the local SQLite vault and lock the terminal from public access."}
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div
            style={{
              background: "rgba(255, 59, 48, 0.15)",
              border: "1px solid rgba(255, 59, 48, 0.35)",
              borderRadius: "10px",
              padding: "12px 14px",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              marginBottom: "20px",
              color: "#ff8080",
              fontSize: "13px"
            }}
          >
            <AlertCircle size={18} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={isInitialized ? handleLogin : handleSetup}>
          <div style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
            <div>
              <label
                htmlFor="master-pwd"
                style={{
                  display: "block",
                  fontSize: "12.5px",
                  fontWeight: 600,
                  color: "#cbd5e1",
                  marginBottom: "8px"
                }}
              >
                {isInitialized ? "Master Password" : "New Master Password"}
              </label>
              <div style={{ position: "relative" }}>
                <input
                  id="master-pwd"
                  type={showPassword ? "text" : "password"}
                  placeholder={isInitialized ? "Enter your master password..." : "At least 6 characters..."}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoFocus
                  required
                  style={{
                    width: "100%",
                    padding: "13px 44px 13px 14px",
                    background: "#080c14",
                    border: "1px solid rgba(255, 255, 255, 0.15)",
                    borderRadius: "10px",
                    color: "#ffffff",
                    fontSize: "14px",
                    outline: "none",
                    boxSizing: "border-box"
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  style={{
                    position: "absolute",
                    right: "12px",
                    top: "50%",
                    transform: "translateY(-50%)",
                    background: "transparent",
                    border: "none",
                    color: "#94a3b8",
                    cursor: "pointer",
                    display: "flex"
                  }}
                  title={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            {!isInitialized && (
              <div>
                <label
                  htmlFor="confirm-master-pwd"
                  style={{
                    display: "block",
                    fontSize: "12.5px",
                    fontWeight: 600,
                    color: "#cbd5e1",
                    marginBottom: "8px"
                  }}
                >
                  Confirm Master Password
                </label>
                <input
                  id="confirm-master-pwd"
                  type={showPassword ? "text" : "password"}
                  placeholder="Re-enter password to confirm..."
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  style={{
                    width: "100%",
                    padding: "13px 14px",
                    background: "#080c14",
                    border: "1px solid rgba(255, 255, 255, 0.15)",
                    borderRadius: "10px",
                    color: "#ffffff",
                    fontSize: "14px",
                    outline: "none",
                    boxSizing: "border-box"
                  }}
                />
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary"
              style={{
                width: "100%",
                padding: "14px",
                fontSize: "15px",
                fontWeight: 700,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px",
                marginTop: "6px",
                cursor: loading ? "wait" : "pointer"
              }}
            >
              {loading ? (
                <span>Verifying Vault Security...</span>
              ) : isInitialized ? (
                <>
                  <Key size={18} /> Unlock Terminal
                </>
              ) : (
                <>
                  <Shield size={18} /> Initialize Security Vault
                </>
              )}
            </button>
          </div>
        </form>

        {/* Security Features Callout */}
        <div
          style={{
            marginTop: "26px",
            paddingTop: "20px",
            borderTop: "1px solid rgba(255, 255, 255, 0.08)",
            display: "flex",
            flexDirection: "column",
            gap: "8px"
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "11.5px", color: "#64748b" }}>
            <CheckCircle2 size={14} color="#00f0ff" />
            <span>Zero-Trust Public Shield: Site and APIs completely locked until unlocked</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "11.5px", color: "#64748b" }}>
            <CheckCircle2 size={14} color="#00f0ff" />
            <span>PBKDF2-HMAC-SHA256 Master Password Hashing (100k rounds)</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "11.5px", color: "#64748b" }}>
            <CheckCircle2 size={14} color="#00f0ff" />
            <span>AES-256 Fernet Encrypted SQLite Vault for Kite & AI Keys</span>
          </div>
        </div>
      </div>
    </div>
  );
};
