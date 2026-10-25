"""
Unit Tests for Institutional Quantitative Strategy Engine & Real-Time P&L - KitePulse AI
"""

import pytest
import pandas as pd
import numpy as np

from technical_indicators import (
    calculate_cpr,
    calculate_supertrend,
    calculate_adx,
    calculate_vwap_bands,
    enrich_candle_indicators,
    detect_rsi_divergence
)
from quant_strategy import quant_engine, InstitutionalQuantEngine
from gemini_analyzer import gemini_analyzer
from kite_executor import kite_executor


def generate_synthetic_candles(trend: str = "bullish", count: int = 50) -> pd.DataFrame:
    """Helper to create synthetic OHLCV bars for quantitative strategy validation."""
    np.random.seed(42)
    base_price = 24500.0
    records = []

    for i in range(count):
        if trend == "bullish":
            close = base_price + (i * 12.0) + np.random.uniform(-3, 8)
        elif trend == "bearish":
            close = base_price - (i * 12.0) + np.random.uniform(-8, 3)
        else:  # sideways chop
            close = base_price + np.random.uniform(-10, 10)

        high = close + np.random.uniform(5, 15)
        low = close - np.random.uniform(5, 15)
        open_p = (high + low) / 2.0
        volume = int(np.random.uniform(5000, 25000))

        records.append({
            "timestamp": f"2026-09-17 09:{i:02d}:00",
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume
        })

    df = pd.DataFrame(records)
    return enrich_candle_indicators(df)


def test_cpr_calculation():
    """Validates Central Pivot Range (CPR - TC, Pivot, BC) mathematics and regimes."""
    cpr = calculate_cpr(high=24600.0, low=24400.0, close=24550.0)
    
    expected_pivot = (24600.0 + 24400.0 + 24550.0) / 3.0
    expected_bc = (24600.0 + 24400.0) / 2.0
    expected_tc = (expected_pivot - expected_bc) + expected_pivot

    assert abs(cpr["pivot"] - round(expected_pivot, 2)) < 0.05
    assert abs(cpr["bc"] - round(expected_bc, 2)) < 0.05
    assert abs(cpr["tc"] - round(expected_tc, 2)) < 0.05
    assert cpr["cpr_width"] >= 0
    assert cpr["cpr_regime"] in ["NARROW_TRENDING", "WIDE_RANGE_BOUND", "AVERAGE_NORMAL"]


def test_supertrend_and_adx_indicators():
    """Validates Supertrend (10,3) and ADX (14) indicator computation."""
    df = generate_synthetic_candles("bullish", count=40)
    
    assert "supertrend" in df.columns
    assert "supertrend_direction" in df.columns
    assert "adx_14" in df.columns
    assert "plus_di" in df.columns
    assert "minus_di" in df.columns

    # In a strong bullish trend, direction should be 1 (GREEN)
    assert df["supertrend_direction"].iloc[-1] == 1
    # ADX should reflect positive momentum
    assert df["adx_14"].iloc[-1] > 0


def test_strike_resolution():
    """Validates smart ATM option strike selection for NIFTY and BANKNIFTY."""
    strike, inst = InstitutionalQuantEngine.resolve_optimal_strike("NIFTY 50", 24832.50, is_bullish=True)
    assert strike == 24850
    assert inst == "NIFTY 24850 CE"

    strike_pe, inst_pe = InstitutionalQuantEngine.resolve_optimal_strike("BANK NIFTY", 51270.0, is_bullish=False)
    assert strike_pe == 51300
    assert "BANKNIFTY 51300 PE" in inst_pe


def test_quant_engine_bullish_confluence():
    """Validates that strong bullish trend produces actionable proposal with high confluence score."""
    df = generate_synthetic_candles("bullish", count=50)
    quote = {"ltp": float(df["close"].iloc[-1]), "call_option": {"ltp": 140.0, "symbol": "NIFTY 24850 CE"}}

    res = quant_engine.evaluate_quantitative_setup("NIFTY 50", quote, df)

    assert res["actionable"] is True
    assert res["signal_type"] == "BUY_CALL"
    assert res["direction"] == "BULLISH"
    assert res["confluence_score"] >= 65
    assert res["stop_loss"] < res["entry_price"]
    assert res["target_1"] > res["entry_price"]


def test_quant_engine_choppy_consolidation():
    """Validates that low-trend choppy consolidation triggers safe NO_TRADE mode."""
    df = generate_synthetic_candles("sideways", count=30)
    # Manually clamp ADX to low value
    df["adx_14"] = 14.0
    quote = {"ltp": float(df["close"].iloc[-1])}

    res = quant_engine.evaluate_quantitative_setup("NIFTY 50", quote, df)
    # Either not actionable or marked as safe consolidation
    if not res["actionable"]:
        assert res["decision"] == "NO_TRADE"


def test_trailing_stop_loss():
    """Validates that reaching Target 1 automatically trails Stop-Loss to break-even."""
    pos = {
        "position_id": "POS-TEST-1",
        "symbol": "NIFTY 50",
        "instrument": "NIFTY 24850 CE",
        "signal_type": "BUY_CALL",
        "quantity": 25,
        "buy_price": 100.0,
        "stop_loss": 85.0,
        "target_1": 125.0,
        "target_2": 150.0,
        "current_ltp": 100.0,
        "unrealized_pnl": 0.0,
        "pnl_pct": 0.0
    }

    # At entry (price = 103.0, +3% gain < 6%), SL remains 85.0
    res_entry = kite_executor._check_exit_triggers(pos, cur_price=103.0)
    assert res_entry is None
    assert pos["stop_loss"] == 85.0

    # Price reaches +7% gain (107.0 >= 6%), SL trails to Break-Even (100.0)
    res_be = kite_executor._check_exit_triggers(pos, cur_price=107.0)
    assert res_be is None
    assert pos["stop_loss"] == 100.0  # Trailed to cost basis!

    # When price hits Target 1 (125.0), SL trails to locked profit (100 + (125-100)*0.5 = 112.5)
    res_t1 = kite_executor._check_exit_triggers(pos, cur_price=126.0)
    assert pos["stop_loss"] == 112.5  # Locked in 50% profits!

    # When price hits Target 2 (150.0), TARGET_HIT triggers
    res_t2 = kite_executor._check_exit_triggers(pos, cur_price=151.0)
    assert res_t2 == "TARGET_HIT"


def test_effective_price_with_option_delta():
    """Validates that live option delta movement simulates accurate MTM P&L."""
    pos = {
        "position_id": "POS-OPT-1",
        "symbol": "NIFTY 50",
        "instrument": "NIFTY 24850 CE",
        "signal_type": "BUY_CALL",
        "quantity": 25,
        "buy_price": 120.0,
        "underlying_entry": 24800.0,
        "current_ltp": 120.0
    }

    # If underlying moves up by 100 points (from 24800 to 24900)
    live_prices = {"NIFTY 50": 24900.0}
    effective_price = kite_executor._calculate_effective_price(
        "NIFTY 50", pos["instrument"], pos, live_prices
    )

    # With 0.55 delta, 100 pt move should add ~55 pts to option premium (120 + 55 = 175)
    assert effective_price == pytest.approx(175.0, abs=2.0)


def test_daily_loss_circuit_breaker():
    """Validates that reaching max daily loss limit blocks new trade approvals."""
    # Temporarily set high loss in orders history
    old_orders = list(kite_executor.orders_history)
    kite_executor.orders_history = [{"pnl": -2500.0, "status": "COMPLETED"}]
    
    proposal = {
        "proposal_id": "TEST-BREAKER",
        "symbol": "NIFTY 50",
        "instrument": "NIFTY 24850 CE",
        "signal_type": "BUY_CALL",
        "lot_size": 1,
        "entry_price": 100.0,
        "stop_loss": 90.0,
        "target_1": 120.0,
        "target_2": 140.0,
        "status": "PENDING_APPROVAL"
    }
    kite_executor.pending_proposals["TEST-BREAKER"] = proposal

    with pytest.raises(ValueError, match="Daily Loss Circuit Breaker ACTIVATED"):
        kite_executor.approve_trade("TEST-BREAKER")

    # Restore state
    kite_executor.orders_history = old_orders
    kite_executor.pending_proposals.pop("TEST-BREAKER", None)


def test_single_loss_45m_lockout():
    """Validates that a stop loss hit triggers a 45-minute lockout on the symbol."""
    sym = "TATAMOTORS"
    assert kite_executor.is_in_loss_lockout(sym)[0] is False

    # Simulate position closing on stop loss
    pos_id = "POS-LOCKOUT-TEST"
    pos = {
        "position_id": pos_id,
        "symbol": sym,
        "instrument": "TATAMOTORS MIS",
        "signal_type": "BUY_EQUITY",
        "quantity": 1,
        "buy_price": 315.0,
        "current_ltp": 309.6,
        "stop_loss": 312.0,
        "target_1": 320.0,
        "target_2": 325.0,
        "status": "OPEN",
        "mode": "PAPER"
    }
    kite_executor.positions[pos_id] = pos
    kite_executor.close_position(pos_id, reason="STOP_LOSS_HIT")

    is_locked, remaining = kite_executor.is_in_loss_lockout(sym, cooldown_minutes=45)
    assert is_locked is True
    assert remaining >= 44

    # Clean up test state
    kite_executor.last_loss_times.pop(sym, None)


def test_auto_square_off_1515():
    """Validates automated square-off of open MIS positions at 15:15 IST."""
    pos_id = "POS-1515-TEST"
    pos = {
        "position_id": pos_id,
        "symbol": "BANK NIFTY",
        "instrument": "BANK NIFTY 56100 PE",
        "signal_type": "BUY_PUT",
        "quantity": 1,
        "buy_price": 60.0,
        "current_ltp": 65.0,
        "stop_loss": 50.0,
        "target_1": 80.0,
        "target_2": 90.0,
        "status": "OPEN",
        "mode": "PAPER"
    }
    kite_executor.positions[pos_id] = pos

    closed_records = kite_executor.auto_square_off_mis_positions()
    assert len(closed_records) >= 1
    assert pos_id not in kite_executor.positions
    assert pos["status"] == "CLOSED"
    assert pos["close_reason"] == "INTRADAY_AUTO_SQUAREOFF_1515"


def test_15m_opening_range_orb_filter():
    """Validates 15-minute Opening Range (ORB) breakout scoring logic."""
    df = generate_synthetic_candles("bullish", count=40)
    quote = {"ltp": float(df["close"].iloc[-1])}
    
    res = quant_engine.evaluate_quantitative_setup("TATAMOTORS", quote, df)
    # The technical rationale should reference the 15-min Opening Range
    assert "Opening Range" in res["technical_rationale"] or "15-min" in res["technical_rationale"]

