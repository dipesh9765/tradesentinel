import React, { useEffect, useState } from "react";
import { Sparkles, ExternalLink, Eye, EyeOff, CheckCircle2, AlertCircle, Check } from "lucide-react";
import { fetchAIConfigApi, saveAIConfigApi, testAIProviderApi } from "../../services/api";
import type { AIConfig } from "../../services/api";

const CUSTOM_MODEL = "__custom__";

interface Message {
  kind: "ok" | "error";
  text: string;
}

export const AIProviderSettings: React.FC = () => {
  const [config, setConfig] = useState<AIConfig | null>(null);
  const [selected, setSelected] = useState("gemini");
  const [model, setModel] = useState("");
  const [customModel, setCustomModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [message, setMessage] = useState<Message | null>(null);

  const applyConfig = (cfg: AIConfig, providerId: string) => {
    setConfig(cfg);
    const info = cfg.providers.find((p) => p.id === providerId);
    if (!info) return;
    setSelected(providerId);
    if (info.models.includes(info.model)) {
      setModel(info.model);
      setCustomModel("");
    } else {
      setModel(CUSTOM_MODEL);
      setCustomModel(info.model);
    }
    setApiKey("");
  };

  useEffect(() => {
    fetchAIConfigApi()
      .then((cfg) => applyConfig(cfg, cfg.active_provider))
      .catch((e) => setMessage({ kind: "error", text: e.message }));
  }, []);

  if (!config) {
    return message ? <div style={{ fontSize: "12px", color: "var(--color-bear)" }}>{message.text}</div> : null;
  }

  const info = config.providers.find((p) => p.id === selected)!;
  const chosenModel = (model === CUSTOM_MODEL ? customModel : model).trim();
  const isActive = config.active_provider === selected;

  const switchProvider = (id: string) => {
    setMessage(null);
    applyConfig(config, id);
  };

  const handleTest = async () => {
    setBusy("test");
    setMessage(null);
    try {
      await testAIProviderApi({
        target_provider: selected,
        model: chosenModel || undefined,
        api_key: apiKey.trim() || undefined
      });
      setMessage({ kind: "ok", text: `${info.label} responded successfully with model "${chosenModel}".` });
    } catch (e: any) {
      setMessage({ kind: "error", text: e.message });
    } finally {
      setBusy(null);
    }
  };

  const handleSave = async () => {
    if (!chosenModel) {
      setMessage({ kind: "error", text: "Enter a model name." });
      return;
    }
    if (!info.has_key && !apiKey.trim()) {
      setMessage({ kind: "error", text: `Add a ${info.label} API key first.` });
      return;
    }
    setBusy("save");
    setMessage(null);
    try {
      const cfg = await saveAIConfigApi({
        provider: selected,
        target_provider: selected,
        model: chosenModel,
        api_key: apiKey.trim() || undefined
      });
      applyConfig(cfg, selected);
      setMessage({ kind: "ok", text: `${info.label} (${chosenModel}) is now the active AI provider.` });
    } catch (e: any) {
      setMessage({ kind: "error", text: e.message });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{
      background: "#0f1523",
      padding: "16px",
      borderRadius: "12px",
      border: "1px solid rgba(255, 255, 255, 0.1)",
      display: "flex",
      flexDirection: "column",
      gap: "14px"
    }}>
      <div>
        <span style={{ fontSize: "13px", fontWeight: 700, color: "#ffffff", display: "flex", alignItems: "center", gap: "6px" }}>
          <Sparkles size={15} color="var(--color-cyan)" /> AI Provider & Model
        </span>
        <span className="form-hint">
          The AI explains each trade. Trade decisions and price levels always come from the rules engine, so the AI can never change your entry or stop-loss.
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "10px" }}>
        {config.providers.map((p) => {
          const active = config.active_provider === p.id;
          const picked = selected === p.id;
          return (
            <div
              key={p.id}
              onClick={() => switchProvider(p.id)}
              style={{
                padding: "12px",
                borderRadius: "10px",
                cursor: "pointer",
                border: `2px solid ${picked ? "var(--color-cyan)" : "rgba(255, 255, 255, 0.1)"}`,
                background: picked ? "rgba(0, 240, 255, 0.12)" : "#101625"
              }}
            >
              <div style={{ fontWeight: 700, fontSize: "13px", color: picked ? "var(--color-cyan)" : "#ffffff" }}>{p.label}</div>
              <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "4px" }}>
                {p.has_key ? "Key saved" : "No key"}{active ? " · Active" : ""}
              </div>
            </div>
          );
        })}
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="ai-model">
          <span>Model</span>
          <span className="form-label-badge">{info.label}</span>
        </label>
        <select
          id="ai-model"
          className="form-input"
          value={model}
          onChange={(e) => setModel(e.target.value)}
        >
          {info.models.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
          <option value={CUSTOM_MODEL}>Custom model id…</option>
        </select>
        {model === CUSTOM_MODEL && (
          <input
            type="text"
            className="form-input"
            style={{ marginTop: "8px" }}
            placeholder="Exact model id from your provider"
            value={customModel}
            onChange={(e) => setCustomModel(e.target.value)}
            autoComplete="off"
          />
        )}
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="ai-api-key">
          <span>{info.label} API Key</span>
          <a
            href={info.key_url}
            target="_blank"
            rel="noreferrer"
            style={{ fontSize: "11.5px", color: "var(--color-cyan)", textDecoration: "none", display: "flex", alignItems: "center", gap: "3px" }}
          >
            Get API key <ExternalLink size={11} />
          </a>
        </label>
        <div className="form-input-container">
          <input
            id="ai-api-key"
            type={showKey ? "text" : "password"}
            className="form-input"
            style={{ paddingRight: "40px" }}
            placeholder={info.key_preview || info.key_hint}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            autoComplete="off"
          />
          <button
            type="button"
            onClick={() => setShowKey(!showKey)}
            className="form-input-action"
            title={showKey ? "Hide key" : "Show key"}
          >
            {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        </div>
        <span className="form-hint">
          {info.has_key ? "A key is saved (encrypted). Leave blank to keep it, or paste a new one to replace it." : "Stored encrypted in your local vault."}
        </span>
      </div>

      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
        <button type="button" onClick={handleTest} disabled={busy !== null} className="btn btn-secondary" style={{ padding: "8px 14px", fontSize: "12.5px" }}>
          {busy === "test" ? "Testing..." : "Test connection"}
        </button>
        <button type="button" onClick={handleSave} disabled={busy !== null} className="btn btn-primary" style={{ padding: "8px 14px", fontSize: "12.5px", display: "flex", alignItems: "center", gap: "6px" }}>
          <Check size={14} /> {busy === "save" ? "Saving..." : isActive ? "Save AI settings" : `Save & use ${info.label}`}
        </button>
      </div>

      {message && (
        <div style={{
          fontSize: "11.5px",
          display: "flex",
          alignItems: "center",
          gap: "6px",
          color: message.kind === "ok" ? "var(--color-bull)" : "var(--color-bear)"
        }}>
          {message.kind === "ok" ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
          <span>{message.text}</span>
        </div>
      )}
    </div>
  );
};
