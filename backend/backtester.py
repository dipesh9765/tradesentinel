"""
Strategy Backtester - KitePulse AI

Replays historical candles through the SAME rules engine and the SAME exit rules the live system
uses, then reports what the strategy would actually have earned after costs.

Realism choices (all deliberately conservative):
    - Signals are generated on a bar's close; the trade is entered at the NEXT bar's open.
    - Inside a bar the adverse price is assumed to be hit before the favourable one (stop first).
    - Slippage, brokerage, STT, exchange fees, stamp duty and GST are charged on every trade.
    - The same daily trade cap, consecutive-loss pause and post-loss lockout as live trading apply.
    - Open positions are squared off at 15:15 IST.

Known limits (reported in every result):
    - No historical option prices are available, so index trades are simulated on a delta model of the
      underlying (no theta / gamma / IV change). Treat option results as approximate.
    - A fixed-rule strategy cannot be "fitted", so the walk-forward folds show stability over time
      (is the edge consistent, or concentrated in one lucky stretch?), not parameter optimisation.

Usage:
    python backtester.py --csv bank_nifty_5m.csv --symbol "BANK NIFTY"
CSV columns: timestamp (or date), open, high, low, close, volume.
"""

import argparse
import datetime
import json
import logging
import math
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from config import is_index_symbol, get_instrument_lot_sizes
from exit_rules import check_exit_triggers
from quant_strategy import quant_engine
from technical_indicators import enrich_candle_indicators
from trade_validation import validate_signal

logger = logging.getLogger(__name__)

WARMUP_BARS = 30
MIN_TRADES_FOR_CONCLUSION = 30


@dataclass
class CostModel:
    """Indian intraday cost structure (approximate current NSE / Zerodha rates)."""
    is_option: bool
    slippage_pct: float
    flat_brokerage: float = 20.0

    def charges(self, buy_value: float, sell_value: float) -> float:
        if self.is_option:
            brokerage = self.flat_brokerage * 2
            stt = 0.001 * sell_value
            exchange = 0.0003503 * (buy_value + sell_value)
        else:
            brokerage = min(self.flat_brokerage, 0.0003 * buy_value) + min(self.flat_brokerage, 0.0003 * sell_value)
            stt = 0.00025 * sell_value
            exchange = 0.0000297 * (buy_value + sell_value)
        sebi = 0.000001 * (buy_value + sell_value)
        stamp = 0.00003 * buy_value
        gst = 0.18 * (brokerage + exchange + sebi)
        return brokerage + stt + exchange + sebi + stamp + gst


def default_costs(is_option: bool) -> CostModel:
    return CostModel(is_option=is_option, slippage_pct=0.5 if is_option else 0.03)


# --------------------------------------------------------------------------- metrics

def summarize(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    nets = [t["net_pnl"] for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)

    equity, peak, max_dd = 0.0, 0.0, 0.0
    streak, longest = 0, 0
    for x in nets:
        equity += x
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        streak = streak + 1 if x <= 0 else 0
        longest = max(longest, streak)

    return {
        "trades": n,
        "win_rate_pct": round(len(wins) / n * 100, 1),
        "net_pnl": round(sum(nets), 2),
        "total_charges": round(sum(t["charges"] for t in trades), 2),
        "avg_win": round(gross_profit / len(wins), 2) if wins else 0.0,
        "avg_loss": round(-gross_loss / len(losses), 2) if losses else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else None,
        "expectancy_per_trade": round(sum(nets) / n, 2),
        "expectancy_r": round(sum(t["r_multiple"] for t in trades) / n, 2),
        "max_drawdown": round(max_dd, 2),
        "longest_losing_streak": longest,
        "best_trade": round(max(nets), 2),
        "worst_trade": round(min(nets), 2),
    }


def walk_forward(trades: List[Dict[str, Any]], folds: int = 3) -> List[Dict[str, Any]]:
    """Splits trades chronologically into equal folds and summarises each."""
    if len(trades) < folds:
        return []
    size = math.ceil(len(trades) / folds)
    out = []
    for k in range(folds):
        chunk = trades[k * size:(k + 1) * size]
        if chunk:
            out.append({"fold": k + 1, "from": chunk[0]["entry_time"], "to": chunk[-1]["exit_time"], **summarize(chunk)})
    return out


# --------------------------------------------------------------------------- simulation

def _hhmm(ts: pd.Timestamp) -> datetime.time:
    return ts.to_pydatetime().time()


def _simulate_trade(df: pd.DataFrame, ts: pd.Series, i: int, signal: Dict[str, Any], symbol: str,
                    qty: int, costs: CostModel, delta: float, square_off: datetime.time) -> Dict[str, Any]:
    """Enters at bar i+1's open and walks forward bar by bar until an exit rule fires."""
    j = i + 1
    day = ts[j].date()
    is_opt = signal["signal_type"] in ("BUY_CALL", "BUY_PUT")
    direction = -1 if signal["signal_type"] in ("BUY_PUT",) else 1
    is_long = "BUY" in signal["signal_type"]
    sig_entry = float(signal["entry_price"])
    close_i = float(df["close"].iloc[i])

    def price_of(u: float) -> float:
        """Instrument price implied by an underlying level."""
        if not is_opt:
            return u
        return max(2.0, sig_entry + direction * delta * (u - close_i))

    raw_fill = price_of(float(df["open"].iloc[j]))
    shift = raw_fill - sig_entry
    pos = {
        "position_id": f"BT-{j}",
        "signal_type": signal["signal_type"],
        "buy_price": raw_fill,
        "stop_loss": float(signal["stop_loss"]) + shift,
        "target_1": float(signal["target_1"]) + shift,
        "target_2": float(signal["target_2"]) + shift,
    }
    initial_risk = abs(raw_fill - pos["stop_loss"])

    exit_price, reason, exit_idx = None, None, j
    k = j
    while k < len(df):
        if ts[k].date() != day:
            exit_price, reason, exit_idx = price_of(float(df["close"].iloc[k - 1])), "EOD", k - 1
            break
        if k > j and _hhmm(ts[k]) >= square_off:
            exit_price, reason, exit_idx = price_of(float(df["open"].iloc[k])), "EOD_SQUAREOFF", k
            break

        o, h, l, c = (float(df[col].iloc[k]) for col in ("open", "high", "low", "close"))
        po, ph, pl, pc = price_of(o), price_of(h), price_of(l), price_of(c)
        lo, hi = min(ph, pl), max(ph, pl)
        path = [po, lo, hi, pc] if is_long else [po, hi, lo, pc]  # adverse extreme first
        for idx, p in enumerate(path):
            if k == j and idx == 0:
                continue  # the open IS the entry fill
            hit = check_exit_triggers(pos, p)
            if hit:
                if idx == 0:
                    exit_price = p  # gapped through the level
                else:
                    exit_price = pos["stop_loss"] if hit == "STOP_LOSS_HIT" else pos["target_2"]
                reason, exit_idx = hit, k
                break
        if reason:
            break
        k += 1
    else:
        exit_price, reason, exit_idx = price_of(float(df["close"].iloc[-1])), "END_OF_DATA", len(df) - 1

    slip = costs.slippage_pct / 100.0
    entry_adj = raw_fill * (1 + slip) if is_long else raw_fill * (1 - slip)
    exit_adj = exit_price * (1 - slip) if is_long else exit_price * (1 + slip)
    per_unit = (exit_adj - entry_adj) if is_long else (entry_adj - exit_adj)
    gross = per_unit * qty
    buy_value = (entry_adj if is_long else exit_adj) * qty
    sell_value = (exit_adj if is_long else entry_adj) * qty
    charges = costs.charges(buy_value, sell_value)
    net = gross - charges
    r_multiple = net / (initial_risk * qty) if initial_risk > 0 else 0.0

    return {
        "symbol": symbol,
        "signal_type": signal["signal_type"],
        "entry_time": str(ts[j]),
        "exit_time": str(ts[exit_idx]),
        "entry_price": round(entry_adj, 2),
        "exit_price": round(exit_adj, 2),
        "quantity": qty,
        "gross_pnl": round(gross, 2),
        "charges": round(charges, 2),
        "net_pnl": round(net, 2),
        "r_multiple": round(r_multiple, 2),
        "exit_reason": reason,
        "confluence_score": signal.get("confluence_score"),
        "_exit_idx": exit_idx,
    }


def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    lots: int = 1,
    lot_size: Optional[int] = None,
    costs: Optional[CostModel] = None,
    option_delta: float = 0.55,
    last_entry: datetime.time = datetime.time(14, 45),
    square_off: datetime.time = datetime.time(15, 15),
    max_trades_per_day: int = 5,
    max_consecutive_losses: int = 3,
    loss_pause_minutes: int = 60,
    loss_lockout_minutes: int = 45,
    folds: int = 3,
) -> Dict[str, Any]:
    """Runs the full strategy over `df` (5-minute OHLCV) and returns trades, metrics and warnings."""
    df = df.copy()
    if "timestamp" not in df.columns:
        if "date" in df.columns:
            df["timestamp"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            raise ValueError("Candles need a 'timestamp' (or 'date') column.")
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            raise ValueError(f"Candles need an '{col}' column.")
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    df = df.sort_values("timestamp").reset_index(drop=True)
    if "ema_9" not in df.columns:
        df = enrich_candle_indicators(df)
    ts = pd.to_datetime(df["timestamp"])

    is_index = is_index_symbol(symbol)
    if lot_size is None:
        lot_size = get_instrument_lot_sizes().get(symbol, 1)
    qty = max(1, lots * lot_size)
    costs = costs or default_costs(is_option=is_index)

    trades: List[Dict[str, Any]] = []
    day_trades: Dict[datetime.date, int] = {}
    day_streak: Dict[datetime.date, int] = {}
    last_loss_time: Optional[pd.Timestamp] = None
    pause_until: Optional[pd.Timestamp] = None

    i = WARMUP_BARS
    while i < len(df) - 1:
        t = ts[i]
        day = t.date()
        if _hhmm(t) >= last_entry or ts[i + 1].date() != day:
            i += 1
            continue
        if day_trades.get(day, 0) >= max_trades_per_day:
            i += 1
            continue
        if pause_until is not None and t < pause_until:
            i += 1
            continue
        if last_loss_time is not None and (t - last_loss_time) < pd.Timedelta(minutes=loss_lockout_minutes):
            i += 1
            continue

        signal = quant_engine.evaluate_quantitative_setup(
            symbol, {"ltp": float(df["close"].iloc[i])}, df.iloc[:i + 1], as_of=t.to_pydatetime()
        )
        if not signal.get("actionable") or validate_signal(signal):
            i += 1
            continue

        trade = _simulate_trade(df, ts, i, signal, symbol, qty, costs, option_delta, square_off)
        exit_idx = trade.pop("_exit_idx")
        trades.append(trade)
        day_trades[day] = day_trades.get(day, 0) + 1

        exit_ts = ts[exit_idx]
        if trade["net_pnl"] < 0:
            last_loss_time = exit_ts
            day_streak[day] = day_streak.get(day, 0) + 1
            if day_streak[day] >= max_consecutive_losses:
                pause_until = exit_ts + pd.Timedelta(minutes=loss_pause_minutes)
        else:
            day_streak[day] = 0
        i = exit_idx + 1

    summary = summarize(trades)
    result = {
        "symbol": symbol,
        "bars": len(df),
        "trading_days": int(ts.dt.date.nunique()),
        "from": str(ts.iloc[0]),
        "to": str(ts.iloc[-1]),
        "summary": summary,
        "walk_forward": walk_forward(trades, folds),
        "trades": trades[-500:],
        "assumptions": {
            "entry": "next bar open after the signal bar",
            "intrabar_order": "adverse price first",
            "slippage_pct_per_side": costs.slippage_pct,
            "quantity": qty,
            "instrument_model": f"delta {option_delta} option proxy (approximate)" if is_index else "underlying equity",
            "squareoff": square_off.strftime("%H:%M"),
            "max_trades_per_day": max_trades_per_day,
        },
        "warnings": _warnings(summary, result_is_option=is_index),
    }
    return result


def _warnings(summary: Dict[str, Any], result_is_option: bool) -> List[str]:
    out: List[str] = []
    n = summary.get("trades", 0)
    if n == 0:
        return ["No trades were generated. Either the filters never aligned in this period or there is too little data."]
    if n < MIN_TRADES_FOR_CONCLUSION:
        out.append(f"Only {n} trades: too few to conclude anything (need {MIN_TRADES_FOR_CONCLUSION}+, ideally several hundred). Results can be pure luck.")
    if summary["net_pnl"] <= 0:
        out.append("The strategy lost money after costs in this period. Do not trade it live as-is.")
    elif summary.get("profit_factor") is not None and summary["profit_factor"] < 1.3:
        out.append("Profit factor below 1.3 leaves little margin for real-world slippage and bad fills.")
    if result_is_option:
        out.append("Option results use a delta proxy on the underlying (no theta, gamma or IV): treat as approximate.")
    return out


# --------------------------------------------------------------------------- CLI

def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Backtest the KitePulse rules engine on 5-minute candles.")
    ap.add_argument("--csv", required=True, help="CSV with timestamp/date, open, high, low, close, volume")
    ap.add_argument("--symbol", required=True, help='Symbol as in instruments.json, e.g. "BANK NIFTY"')
    ap.add_argument("--lots", type=int, default=1)
    ap.add_argument("--lot-size", type=int, default=None, help="Override units per lot (or shares for equities)")
    ap.add_argument("--out", help="Write the full JSON result here")
    args = ap.parse_args(argv)

    result = run_backtest(load_csv(args.csv), args.symbol, lots=args.lots, lot_size=args.lot_size)
    print(json.dumps({k: v for k, v in result.items() if k != "trades"}, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
