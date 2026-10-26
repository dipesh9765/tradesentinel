import { useCallback, useEffect, useRef, useState } from "react";
import { fetchAuthStatus, logoutApi, setOnUnauthorized } from "../services/api";
import { GenConsts, type AuthStateType } from "../constants";

interface Options {
    /** Called whenever the user becomes authenticated (on load or after login). */
    onAuthenticated: () => void;
}

/** Owns the vault/auth state machine: CHECKING -> UNINITIALIZED | UNAUTHENTICATED | AUTHENTICATED. */
export function useAuthSession({ onAuthenticated }: Options) {
    const [authState, setAuthState] = useState<AuthStateType>(GenConsts.AUTH_STATES.CHECKING);
    const onAuthenticatedRef = useRef(onAuthenticated);

    useEffect(() => {
        onAuthenticatedRef.current = onAuthenticated;
    }, [onAuthenticated]);

    useEffect(() => {
        setOnUnauthorized(() => setAuthState(GenConsts.AUTH_STATES.UNAUTHENTICATED));

        let cancelled = false;
        (async () => {
            try {
                const res = await fetchAuthStatus();
                if (cancelled) return;
                if (!res.is_initialized) {
                    setAuthState(GenConsts.AUTH_STATES.UNINITIALIZED);
                } else if (!res.is_authenticated) {
                    setAuthState(GenConsts.AUTH_STATES.UNAUTHENTICATED);
                } else {
                    setAuthState(GenConsts.AUTH_STATES.AUTHENTICATED);
                    onAuthenticatedRef.current();
                }
            } catch {
                if (!cancelled) setAuthState(GenConsts.AUTH_STATES.UNAUTHENTICATED);
            }
        })();

        return () => {
            cancelled = true;
        };
    }, []);

    const markAuthenticated = useCallback(() => {
        setAuthState(GenConsts.AUTH_STATES.AUTHENTICATED);
        onAuthenticatedRef.current();
    }, []);

    const markUnauthenticated = useCallback(() => {
        setAuthState(GenConsts.AUTH_STATES.UNAUTHENTICATED);
    }, []);

    const logout = useCallback(async () => {
        await logoutApi();
        setAuthState(GenConsts.AUTH_STATES.UNAUTHENTICATED);
    }, []);

    return { authState, markAuthenticated, markUnauthenticated, logout };
}
