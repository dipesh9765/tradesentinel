import { useCallback, useEffect, useRef, useState } from "react";
import confetti from "canvas-confetti";
import { approveTradeApi, closePositionApi, rejectTradeApi, requestAiScan } from "../services/api";
import { GenConsts, type AuthStateType } from "../constants";
import { notificationManager } from "../services/notifications";
import { showAlert } from "../services/dialogs";
import { soundManager } from "../services/sound";
import { errorMessage } from "../utils/errors";
import type { TradeProposal } from "../types";

interface Options {
    authState: AuthStateType;
    selectedSymbol: string;
    kiteConnected: boolean;
    onNeedsKiteSetup: () => void;
    refreshAfterTrade: () => Promise<void>;
    loadHistory: () => Promise<void>;
}

/** Scan / approve / reject / close flows plus the A, R, S keyboard shortcuts. */
export function useTradeActions({
    authState,
    selectedSymbol,
    kiteConnected,
    onNeedsKiteSetup,
    refreshAfterTrade,
    loadHistory,
}: Options) {
    const [proposal, setProposal] = useState<TradeProposal | null>(null);
    const [isScanning, setIsScanning] = useState(false);

    const triggerScan = useCallback(
        async (symbol: string) => {
            if (!kiteConnected) {
                showAlert(
                    "Zerodha Kite Connect is not configured or authenticated. Please add credentials in Settings to scan live market setups.",
                );
                onNeedsKiteSetup();
                return;
            }
            setIsScanning(true);
            soundManager.playClick();
            try {
                const next = await requestAiScan(symbol);
                setProposal(next);
                await loadHistory();
                soundManager.playAlert();
                notificationManager.notifyTradeProposal(next);
            } catch (err) {
                showAlert("Scan failed: " + errorMessage(err));
            } finally {
                setIsScanning(false);
            }
        },
        [kiteConnected, onNeedsKiteSetup, loadHistory],
    );

    const approve = useCallback(
        async (proposalId: string) => {
            try {
                soundManager.playSuccess();
                await approveTradeApi(proposalId);
                setProposal(null);
                await refreshAfterTrade();
                confetti({ particleCount: 50, spread: 60, origin: { y: 0.6 } });
            } catch (err) {
                showAlert("Trade execution error: " + errorMessage(err));
            }
        },
        [refreshAfterTrade],
    );

    const reject = useCallback(
        async (proposalId: string) => {
            try {
                soundManager.playClick();
                await rejectTradeApi(proposalId);
                setProposal(null);
                await loadHistory();
            } catch (err) {
                showAlert("Rejection error: " + errorMessage(err));
            }
        },
        [loadHistory],
    );

    const closePosition = useCallback(
        async (positionId: string) => {
            try {
                soundManager.playClick();
                await closePositionApi(positionId);
                await refreshAfterTrade();
            } catch (err) {
                showAlert("Failed to close position: " + errorMessage(err));
            }
        },
        [refreshAfterTrade],
    );

    /** A proposal pushed by the server (scanner alert). */
    const receiveProposal = useCallback((next: TradeProposal) => {
        setProposal(next);
        soundManager.playAlert();
        notificationManager.notifyTradeProposal(next);
    }, []);

    const clearProposal = useCallback(() => setProposal(null), []);

    // Keyboard shortcuts read the latest handlers/proposal through a ref.
    const latest = useRef({ proposal, selectedSymbol, approve, reject, triggerScan });
    useEffect(() => {
        latest.current = { proposal, selectedSymbol, approve, reject, triggerScan };
    });

    useEffect(() => {
        if (authState !== GenConsts.AUTH_STATES.AUTHENTICATED) return;

        const onKeyDown = (e: KeyboardEvent) => {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

            const { proposal: active, selectedSymbol: symbol, approve: doApprove, reject: doReject, triggerScan: doScan } =
                latest.current;
            if (active && active.status === GenConsts.STATUSES.PENDING_APPROVAL) {
                if (e.key === "a" || e.key === "A" || e.key === "Enter") {
                    e.preventDefault();
                    void doApprove(active.proposal_id);
                } else if (e.key === "r" || e.key === "R" || e.key === "Escape") {
                    e.preventDefault();
                    void doReject(active.proposal_id);
                }
            } else if (e.key === "s" || e.key === "S") {
                e.preventDefault();
                void doScan(symbol);
            }
        };

        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [authState]);

    return { proposal, isScanning, triggerScan, approve, reject, closePosition, receiveProposal, clearProposal };
}
