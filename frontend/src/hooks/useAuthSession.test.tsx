import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { GenConsts } from "../constants";

vi.mock("../services/api", () => ({
    fetchAuthStatus: vi.fn(),
    logoutApi: vi.fn().mockResolvedValue(undefined),
    setOnUnauthorized: vi.fn(),
}));

import { fetchAuthStatus, logoutApi, setOnUnauthorized } from "../services/api";
import { useAuthSession } from "./useAuthSession";

const STATES = GenConsts.AUTH_STATES;

describe("useAuthSession", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("starts in CHECKING", () => {
        vi.mocked(fetchAuthStatus).mockReturnValue(new Promise(() => {}));
        const { result } = renderHook(() => useAuthSession({ onAuthenticated: vi.fn() }));
        expect(result.current.authState).toBe(STATES.CHECKING);
    });

    it("reports UNINITIALIZED when no vault exists", async () => {
        vi.mocked(fetchAuthStatus).mockResolvedValue({ is_initialized: false, is_authenticated: false, is_vault_unlocked: false });
        const { result } = renderHook(() => useAuthSession({ onAuthenticated: vi.fn() }));
        await waitFor(() => expect(result.current.authState).toBe(STATES.UNINITIALIZED));
    });

    it("reports UNAUTHENTICATED when the vault is locked", async () => {
        vi.mocked(fetchAuthStatus).mockResolvedValue({ is_initialized: true, is_authenticated: false, is_vault_unlocked: false });
        const { result } = renderHook(() => useAuthSession({ onAuthenticated: vi.fn() }));
        await waitFor(() => expect(result.current.authState).toBe(STATES.UNAUTHENTICATED));
    });

    it("authenticates and fires the callback once for a valid session", async () => {
        vi.mocked(fetchAuthStatus).mockResolvedValue({ is_initialized: true, is_authenticated: true, is_vault_unlocked: true });
        const onAuthenticated = vi.fn();
        const { result } = renderHook(() => useAuthSession({ onAuthenticated }));
        await waitFor(() => expect(result.current.authState).toBe(STATES.AUTHENTICATED));
        expect(onAuthenticated).toHaveBeenCalledTimes(1);
    });

    it("falls back to UNAUTHENTICATED when the status call fails", async () => {
        vi.mocked(fetchAuthStatus).mockRejectedValue(new Error("network"));
        const { result } = renderHook(() => useAuthSession({ onAuthenticated: vi.fn() }));
        await waitFor(() => expect(result.current.authState).toBe(STATES.UNAUTHENTICATED));
    });

    it("drops to UNAUTHENTICATED when the API reports a 401", async () => {
        vi.mocked(fetchAuthStatus).mockResolvedValue({ is_initialized: true, is_authenticated: true, is_vault_unlocked: true });
        const { result } = renderHook(() => useAuthSession({ onAuthenticated: vi.fn() }));
        await waitFor(() => expect(result.current.authState).toBe(STATES.AUTHENTICATED));

        const handler = vi.mocked(setOnUnauthorized).mock.calls[0][0];
        act(() => handler());
        expect(result.current.authState).toBe(STATES.UNAUTHENTICATED);
    });

    it("markAuthenticated runs the callback; logout locks the session", async () => {
        vi.mocked(fetchAuthStatus).mockResolvedValue({ is_initialized: true, is_authenticated: false, is_vault_unlocked: false });
        const onAuthenticated = vi.fn();
        const { result } = renderHook(() => useAuthSession({ onAuthenticated }));
        await waitFor(() => expect(result.current.authState).toBe(STATES.UNAUTHENTICATED));

        act(() => result.current.markAuthenticated());
        expect(result.current.authState).toBe(STATES.AUTHENTICATED);
        expect(onAuthenticated).toHaveBeenCalledTimes(1);

        await act(() => result.current.logout());
        expect(logoutApi).toHaveBeenCalled();
        expect(result.current.authState).toBe(STATES.UNAUTHENTICATED);
    });
});
