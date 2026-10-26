import { useEffect } from "react";
import { verifyAuthTokenApi } from "../services/api";
import { GenConsts, type AuthStateType } from "../constants";

interface Options {
    authState: AuthStateType;
    onKiteStatus: (connected: boolean) => void;
    onSessionLost: () => void;
}

/** Re-verifies the app session and the Kite token on an interval while authenticated. */
export function useTokenHeartbeat({ authState, onKiteStatus, onSessionLost }: Options) {
    useEffect(() => {
        if (authState !== GenConsts.AUTH_STATES.AUTHENTICATED) return;

        const id = setInterval(async () => {
            try {
                const res = await verifyAuthTokenApi();
                if (res.kite_token_check && res.kite_token_check.valid !== undefined) {
                    onKiteStatus(Boolean(res.kite_token_check.valid));
                }
            } catch (err) {
                console.warn("Token verification failed:", err);
                onSessionLost();
            }
        }, GenConsts.INTERVALS.KITE_VERIFY_MS);

        return () => clearInterval(id);
    }, [authState, onKiteStatus, onSessionLost]);
}
