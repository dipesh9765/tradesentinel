import { useEffect, useState } from "react";
import { fetchCandles } from "../services/api";
import { GenConsts } from "../constants";
import { errorMessage } from "../utils/errors";
import type { Candle } from "../types";

interface CandleResult {
    symbol: string;
    candles: Candle[];
    status: string;
    errorDetail: string | null;
}

/** Loads candles for a symbol and keeps them fresh on a polling interval. */
export function useCandles(symbol: string, enabled: boolean) {
    const [result, setResult] = useState<CandleResult | null>(null);

    useEffect(() => {
        if (!enabled || !symbol) return;

        let cancelled = false;
        const load = async () => {
            let next: CandleResult;
            try {
                const res = await fetchCandles(symbol);
                const list = res.candles || [];
                next = {
                    symbol,
                    candles: list,
                    status: res.status || (list.length > 0 ? GenConsts.CHART_STATUSES.OK : GenConsts.CHART_STATUSES.NO_DATA),
                    errorDetail: res.error_detail || res.message || null,
                };
            } catch (err) {
                console.warn("Failed to load candles:", err);
                next = {
                    symbol,
                    candles: [],
                    status: GenConsts.CHART_STATUSES.KITE_BROKER_ERROR,
                    errorDetail: errorMessage(err, "Failed to reach market data service."),
                };
            }
            if (!cancelled) setResult(next);
        };

        void load();
        const id = setInterval(load, GenConsts.INTERVALS.CANDLE_POLL_MS);
        return () => {
            cancelled = true;
            clearInterval(id);
        };
    }, [symbol, enabled]);

    // Results are keyed by symbol, so switching symbols reads as "loading" until the new data lands.
    const current = result && result.symbol === symbol ? result : null;
    const noSymbol = !symbol;
    return {
        candles: current?.candles ?? [],
        isLoading: enabled && !noSymbol && current === null,
        status: noSymbol ? GenConsts.CHART_STATUSES.NO_DATA : (current?.status ?? null),
        errorDetail: current?.errorDetail ?? null,
    };
}
