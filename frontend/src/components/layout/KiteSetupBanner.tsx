import { ShieldAlert } from "lucide-react";

interface KiteSetupBannerProps {
    onConfigure: () => void;
}

/** Shown while no Kite session is active, since market data and live trading need one. */
export function KiteSetupBanner({ onConfigure }: KiteSetupBannerProps) {
    return (
        <div
            role="alert"
            style={{
                background: "color-mix(in srgb, var(--color-warn) 12%, transparent)",
                border: "1px solid color-mix(in srgb, var(--color-warn) 40%, transparent)",
                borderRadius: "14px",
                padding: "14px 18px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "16px",
                flexWrap: "wrap",
                gap: "12px",
            }}
        >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                <div style={{ background: "color-mix(in srgb, var(--color-warn) 20%, transparent)", padding: "8px", borderRadius: "8px", display: "flex" }}>
                    <ShieldAlert size={22} color="var(--color-warn)" />
                </div>
                <div>
                    <div style={{ fontWeight: 800, color: "var(--color-warn)", fontSize: "14px", }}>
                        Zerodha Kite Connect Setup Required (Real Data Mode)
                    </div>
                    <div style={{ color: "var(--color-ink-soft)", fontSize: "12px", marginTop: "2px" }}>
                        Authenticate today's Kite session in Settings to stream authentic NSE/NFO market quotes and live charts.
                    </div>
                </div>
            </div>
            <button
                onClick={onConfigure}
                className="btn btn-primary"
                style={{
                    padding: "8px 16px",
                    fontSize: "12.5px",
                    fontWeight: 700,
                    background: "var(--color-warn)",
                    color: "var(--color-raised)",
                    borderColor: "var(--color-warn)",
                }}
            >
                Configure Kite Credentials
            </button>
        </div>
    );
}
