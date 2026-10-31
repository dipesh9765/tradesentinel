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
                background: "rgba(255, 179, 0, 0.12)",
                border: "1px solid rgba(255, 179, 0, 0.4)",
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
                <div style={{ background: "rgba(255, 179, 0, 0.2)", padding: "8px", borderRadius: "8px", display: "flex" }}>
                    <ShieldAlert size={22} color="#ffb300" />
                </div>
                <div>
                    <div style={{ fontWeight: 800, color: "#ffb300", fontSize: "14px", letterSpacing: "0.2px" }}>
                        Zerodha Kite Connect Setup Required (Real Data Mode)
                    </div>
                    <div style={{ color: "#cbd5e1", fontSize: "12px", marginTop: "2px" }}>
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
                    background: "#ffb300",
                    color: "#0c111d",
                    borderColor: "#ffb300",
                }}
            >
                Configure Kite Credentials
            </button>
        </div>
    );
}
