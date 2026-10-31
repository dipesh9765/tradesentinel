import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { GenConsts } from "../constants";
import type { Candle } from "../types";

vi.mock("../services/api", () => ({ fetchCandles: vi.fn() }));

import { fetchCandles } from "../services/api";
import { useCandles } from "./useCandles";

const CANDLE = { time: "2026-10-26 09:15:00", open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 } as Candle;

describe("useCandles", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("does nothing while disabled", () => {
        const { result } = renderHook(() => useCandles("NIFTY 50", false));
        expect(fetchCandles).not.toHaveBeenCalled();
        expect(result.current.candles).toEqual([]);
        expect(result.current.isLoading).toBe(false);
    });

    it("reports NO_DATA without a symbol", () => {
        const { result } = renderHook(() => useCandles("", true));
        expect(fetchCandles).not.toHaveBeenCalled();
        expect(result.current.status).toBe(GenConsts.CHART_STATUSES.NO_DATA);
    });

    it("loads candles and derives an OK status", async () => {
        vi.mocked(fetchCandles).mockResolvedValue({ candles: [CANDLE] } as Awaited<ReturnType<typeof fetchCandles>>);
        const { result } = renderHook(() => useCandles("NIFTY 50", true));
        expect(result.current.isLoading).toBe(true);
        await waitFor(() => expect(result.current.isLoading).toBe(false));
        expect(result.current.candles).toEqual([CANDLE]);
        expect(result.current.status).toBe(GenConsts.CHART_STATUSES.OK);
    });

    it("exposes a broker error state when the request fails", async () => {
        vi.mocked(fetchCandles).mockRejectedValue(new Error("gateway timeout"));
        const { result } = renderHook(() => useCandles("NIFTY 50", true));
        await waitFor(() => expect(result.current.status).toBe(GenConsts.CHART_STATUSES.KITE_BROKER_ERROR));
        expect(result.current.errorDetail).toBe("gateway timeout");
        expect(result.current.candles).toEqual([]);
    });

    it("shows loading again and drops stale candles when the symbol changes", async () => {
        vi.mocked(fetchCandles).mockResolvedValue({ candles: [CANDLE] } as Awaited<ReturnType<typeof fetchCandles>>);
        const { result, rerender } = renderHook(({ s }) => useCandles(s, true), { initialProps: { s: "NIFTY 50" } });
        await waitFor(() => expect(result.current.candles).toHaveLength(1));

        vi.mocked(fetchCandles).mockReturnValue(new Promise(() => {}));
        rerender({ s: "BANK NIFTY" });
        expect(result.current.isLoading).toBe(true);
        expect(result.current.candles).toEqual([]);
    });
});
