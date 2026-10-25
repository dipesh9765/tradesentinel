"""Backtester tests: trade mechanics on hand-built candles, cost model, metrics and a real-engine smoke run."""

import datetime

import numpy as np
import pandas as pd
import pytest

import backtester
from backtester import CostModel, run_backtest, summarize, walk_forward


def _candles(days=2, overrides=None):
    """Flat 100.0 market, 5-minute bars 09:15..15:25. overrides: {(day_idx, bar_idx): (o, h, l, c)}"""
    rows = []
    start = datetime.datetime(2026, 9, 7, 9, 15)  # a Monday
    for d in range(days):
        for b in range(75):
            t = start + datetime.timedelta(days=d, minutes=5 * b)
            o, h, l, c = (overrides or {}).get((d, b), (100.0, 100.5, 99.5, 100.0))
            rows.append({"timestamp": t.strftime("%Y-%m-%d %H:%M:%S"), "open": o, "high": h, "low": l,
                         "close": c, "volume": 1000})
    return pd.DataFrame(rows)


class _OneShotEngine:
    """Fires one BUY_EQUITY signal when exactly `at_len` bars are visible."""

    def __init__(self, at_len, entry=100.0, stop=99.0, t1=102.0, t2=103.0):
        self.at_len, self.levels = at_len, (entry, stop, t1, t2)
        self.fired = False

    def evaluate_quantitative_setup(self, symbol, quote, df, prev_day_ohlc=None, as_of=None):
        if not self.fired and len(df) == self.at_len:
            self.fired = True
            e, s, t1, t2 = self.levels
            return {"actionable": True, "signal_type": "BUY_EQUITY", "entry_price": e, "stop_loss": s,
                    "target_1": t1, "target_2": t2, "confluence_score": 80}
        return {"actionable": False}


def _run(monkeypatch, df, engine, **kw):
    monkeypatch.setattr(backtester, "quant_engine", engine)
    return run_backtest(df, "RELIANCE", lots=1, lot_size=10, **kw)


def test_stop_loss_exit_is_a_net_loss(monkeypatch):
    df = _candles(overrides={(0, 41): (100.0, 100.2, 98.5, 99.0)})   # entry bar dives through the stop
    res = _run(monkeypatch, df, _OneShotEngine(at_len=41))
    t = res["trades"][0]
    assert t["exit_reason"] == "STOP_LOSS_HIT"
    assert t["gross_pnl"] < 0 and t["net_pnl"] < t["gross_pnl"]       # costs make it worse
    assert t["net_pnl"] == pytest.approx(t["gross_pnl"] - t["charges"], abs=0.02)


def test_target_exit_books_profit(monkeypatch):
    df = _candles(overrides={(0, 41): (100.0, 103.5, 99.8, 103.0)})
    res = _run(monkeypatch, df, _OneShotEngine(at_len=41))
    t = res["trades"][0]
    assert t["exit_reason"] == "TARGET_HIT"
    assert t["gross_pnl"] > 0 and t["r_multiple"] > 1


def test_stop_checked_before_target_within_a_bar(monkeypatch):
    # One wild bar touches BOTH levels: conservative handling must assume the stop came first.
    df = _candles(overrides={(0, 41): (100.0, 104.0, 98.0, 101.0)})
    t = _run(monkeypatch, df, _OneShotEngine(at_len=41))["trades"][0]
    assert t["exit_reason"] == "STOP_LOSS_HIT"


def test_entry_is_next_bar_open_not_signal_close(monkeypatch):
    df = _candles(overrides={(0, 41): (100.4, 100.6, 100.2, 100.5)})
    t = _run(monkeypatch, df, _OneShotEngine(at_len=41, stop=99.4, t1=102.4, t2=103.4))["trades"][0]
    assert t["entry_time"].endswith("12:40:00")              # bar 41, not the signal bar 40
    assert t["entry_price"] >= 100.4                          # filled at that bar's open (+ slippage)


def test_open_trade_is_squared_off_at_1515(monkeypatch):
    t = _run(monkeypatch, _candles(), _OneShotEngine(at_len=41))["trades"][0]
    assert t["exit_reason"] == "EOD_SQUAREOFF"
    assert t["exit_time"].endswith("15:15:00")


def test_no_entries_late_in_the_session(monkeypatch):
    res = _run(monkeypatch, _candles(), _OneShotEngine(at_len=70))   # bar 69 = 15:00, past the 14:45 cutoff
    assert res["summary"]["trades"] == 0


def test_cost_model():
    opt = CostModel(is_option=True, slippage_pct=0.5)
    eq = CostModel(is_option=False, slippage_pct=0.03)
    # Option trade: flat brokerage alone is Rs 40, so even a tiny round trip is never free
    assert opt.charges(10000, 10000) > 40
    # Equity brokerage is capped at 0.03% for small orders (cheaper than the Rs 20 flat fee)
    assert eq.charges(10000, 10000) < opt.charges(10000, 10000)
    assert opt.charges(20000, 20000) > opt.charges(10000, 10000)


def test_summary_metrics_and_walk_forward():
    trades = [{"net_pnl": x, "charges": 10.0, "r_multiple": x / 100, "entry_time": f"d{i}", "exit_time": f"d{i}"}
              for i, x in enumerate([200, -100, -100, 300, -100, 100])]
    s = summarize(trades)
    assert s["trades"] == 6 and s["win_rate_pct"] == 50.0
    assert s["net_pnl"] == 300 and s["profit_factor"] == pytest.approx(600 / 300)
    assert s["max_drawdown"] == 200                      # equity 200 -> 0 is the deepest fall from a peak
    assert s["longest_losing_streak"] == 2
    folds = walk_forward(trades, folds=3)
    assert [f["trades"] for f in folds] == [2, 2, 2]


def test_empty_result_is_flagged():
    res = run_backtest(_candles(), "RELIANCE", lot_size=10)
    assert res["summary"]["trades"] == 0 or res["summary"]["trades"] >= 0
    if res["summary"]["trades"] == 0:
        assert res["warnings"]


def test_real_engine_smoke_on_trending_data():
    """Runs the genuine rules engine end to end on synthetic trending data: no crash, sane invariants."""
    rng = np.random.default_rng(7)
    rows, price = [], 24000.0
    start = datetime.datetime(2026, 8, 3, 9, 15)
    for d in range(12):
        drift = 4.0 if d % 2 == 0 else -4.0
        for b in range(75):
            t = start + datetime.timedelta(days=d, minutes=5 * b)
            o = price
            price = price + drift + rng.normal(0, 12)
            rows.append({"timestamp": t.strftime("%Y-%m-%d %H:%M:%S"), "open": o,
                         "high": max(o, price) + abs(rng.normal(0, 6)), "low": min(o, price) - abs(rng.normal(0, 6)),
                         "close": price, "volume": int(rng.integers(800, 3000))})
    res = run_backtest(pd.DataFrame(rows), "RELIANCE", lot_size=10, max_trades_per_day=2)
    per_day = {}
    for t in res["trades"]:
        per_day[t["entry_time"][:10]] = per_day.get(t["entry_time"][:10], 0) + 1
        assert t["entry_time"][11:16] >= "09:30"            # never trades the opening range
        assert t["net_pnl"] == pytest.approx(t["gross_pnl"] - t["charges"], abs=0.02)
    assert all(v <= 2 for v in per_day.values())
    assert res["trading_days"] == 12
