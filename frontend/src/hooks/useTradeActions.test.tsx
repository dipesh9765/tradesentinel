import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { GenConsts } from "../constants";
import type { TradeProposal } from "../types";

vi.mock("../services/api", () => ({
    requestAiScan: vi.fn(),
    approveTradeApi: vi.fn(),
    rejectTradeApi: vi.fn(),
    closePositionApi: vi.fn(),
}));
vi.mock("../services/dialogs", () => ({ showAlert: vi.fn() }));
vi.mock("../services/sound", () => ({
    soundManager: { playClick: vi.fn(), playAlert: vi.fn(), playSuccess: vi.fn() },
}));
vi.mock("../services/notifications", () => ({ notificationManager: { notifyTradeProposal: vi.fn() } }));
vi.mock("canvas-confetti", () => ({ default: vi.fn() }));

import { approveTradeApi, closePositionApi, rejectTradeApi, requestAiScan } from "../services/api";
import { showAlert } from "../services/dialogs";
import { useTradeActions } from "./useTradeActions";

const PROPOSAL = {
    proposal_id: "p-1",
    status: GenConsts.STATUSES.PENDING_APPROVAL,
} as unknown as TradeProposal;

function setup(overrides: Partial<Parameters<typeof useTradeActions>[0]> = {}) {
    const props = {
        authState: GenConsts.AUTH_STATES.AUTHENTICATED,
        selectedSymbol: "NIFTY 50",
        kiteConnected: true,
        onNeedsKiteSetup: vi.fn(),
        refreshAfterTrade: vi.fn().mockResolvedValue(undefined),
        loadHistory: vi.fn().mockResolvedValue(undefined),
        ...overrides,
    };
    return { props, ...renderHook(() => useTradeActions(props)) };
}

function press(key: string, target: EventTarget = window) {
    const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
    act(() => {
        target.dispatchEvent(event);
    });
    return event;
}

describe("useTradeActions", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("refuses to scan without a Kite session and opens setup instead", async () => {
        const { result, props } = setup({ kiteConnected: false });
        await act(() => result.current.triggerScan("NIFTY 50"));
        expect(requestAiScan).not.toHaveBeenCalled();
        expect(showAlert).toHaveBeenCalledWith(expect.stringContaining("not configured"));
        expect(props.onNeedsKiteSetup).toHaveBeenCalled();
    });

    it("stores the proposal returned by a scan and refreshes history", async () => {
        vi.mocked(requestAiScan).mockResolvedValue(PROPOSAL);
        const { result, props } = setup();
        await act(() => result.current.triggerScan("NIFTY 50"));
        expect(result.current.proposal).toEqual(PROPOSAL);
        expect(props.loadHistory).toHaveBeenCalled();
        expect(result.current.isScanning).toBe(false);
    });

    it("reports a failed scan and clears the scanning flag", async () => {
        vi.mocked(requestAiScan).mockRejectedValue(new Error("No trade: weak trend"));
        const { result } = setup();
        await act(() => result.current.triggerScan("NIFTY 50"));
        expect(showAlert).toHaveBeenCalledWith("Scan failed: No trade: weak trend");
        expect(result.current.isScanning).toBe(false);
        expect(result.current.proposal).toBeNull();
    });

    it("approving clears the proposal and refreshes server state", async () => {
        vi.mocked(approveTradeApi).mockResolvedValue({});
        const { result, props } = setup();
        act(() => result.current.receiveProposal(PROPOSAL));
        await act(() => result.current.approve("p-1"));
        expect(approveTradeApi).toHaveBeenCalledWith("p-1");
        expect(result.current.proposal).toBeNull();
        expect(props.refreshAfterTrade).toHaveBeenCalled();
    });

    it("keeps the proposal when approval fails", async () => {
        vi.mocked(approveTradeApi).mockRejectedValue(new Error("Daily trade limit reached"));
        const { result } = setup();
        act(() => result.current.receiveProposal(PROPOSAL));
        await act(() => result.current.approve("p-1"));
        expect(showAlert).toHaveBeenCalledWith("Trade execution error: Daily trade limit reached");
        expect(result.current.proposal).toEqual(PROPOSAL);
    });

    it("rejecting clears the proposal", async () => {
        vi.mocked(rejectTradeApi).mockResolvedValue({});
        const { result } = setup();
        act(() => result.current.receiveProposal(PROPOSAL));
        await act(() => result.current.reject("p-1"));
        expect(rejectTradeApi).toHaveBeenCalledWith("p-1");
        expect(result.current.proposal).toBeNull();
    });

    it("closing a position refreshes state", async () => {
        vi.mocked(closePositionApi).mockResolvedValue({});
        const { result, props } = setup();
        await act(() => result.current.closePosition("pos-9"));
        expect(closePositionApi).toHaveBeenCalledWith("pos-9");
        expect(props.refreshAfterTrade).toHaveBeenCalled();
    });

    it("A approves and R rejects a pending proposal", async () => {
        vi.mocked(approveTradeApi).mockResolvedValue({});
        vi.mocked(rejectTradeApi).mockResolvedValue({});
        const { result } = setup();
        act(() => result.current.receiveProposal(PROPOSAL));

        press("a");
        await waitFor(() => expect(approveTradeApi).toHaveBeenCalledWith("p-1"));

        act(() => result.current.receiveProposal(PROPOSAL));
        press("Escape");
        await waitFor(() => expect(rejectTradeApi).toHaveBeenCalledWith("p-1"));
    });

    it("S starts a scan when no proposal is pending", async () => {
        vi.mocked(requestAiScan).mockResolvedValue(PROPOSAL);
        setup();
        press("s");
        await waitFor(() => expect(requestAiScan).toHaveBeenCalledWith("NIFTY 50"));
    });

    it("ignores shortcuts typed into form fields", () => {
        setup();
        const input = document.createElement("input");
        document.body.appendChild(input);
        press("s", input);
        expect(requestAiScan).not.toHaveBeenCalled();
        input.remove();
    });

    it("ignores shortcuts while logged out", () => {
        setup({ authState: GenConsts.AUTH_STATES.UNAUTHENTICATED });
        press("s");
        expect(requestAiScan).not.toHaveBeenCalled();
    });
});
