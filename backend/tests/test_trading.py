import pandas as pd

from kite_executor import KiteTradingExecutor, OrderStatus
from market_data import MarketDataManager
from technical_indicators import (
    enrich_candle_indicators,
)
from trade_analyzer import TradeAnalyzer


def test_indicators():
    df = pd.DataFrame(
        {
            "timestamp": [f"2026-09-12 09:{i:02d}:00" for i in range(30)],
            "open": [100.0 + i for i in range(30)],
            "high": [105.0 + i for i in range(30)],
            "low": [98.0 + i for i in range(30)],
            "close": [102.0 + i for i in range(30)],
            "volume": [1000 + i * 50 for i in range(30)],
        }
    )
    enriched = enrich_candle_indicators(df)
    assert "ema_9" in enriched.columns
    assert "ema_21" in enriched.columns
    assert "rsi_14" in enriched.columns
    assert "vwap" in enriched.columns
    assert "atr_14" in enriched.columns
    assert len(enriched) == 30
    assert enriched["rsi_14"].iloc[-1] > 0


def test_market_data_manager_unconfigured_no_dummy_data():
    mdm = MarketDataManager()
    assert mdm.is_configured() is False
    quotes = mdm.get_all_quotes()
    assert len(quotes) >= 1

    bn = mdm.get_quote("BANK NIFTY")
    assert bn["symbol"] == "BANK NIFTY"
    # No fake dummy LTP fabricated when unconfigured
    assert bn["configured"] is False
    assert bn["status"] == "CONFIG_REQUIRED"

    # Never generates fake simulated candles
    candles = mdm.get_candles("BANK NIFTY", limit=20)
    assert len(candles) == 0


def test_analyzer_returns_no_trade_without_data():
    """With no market data the analyzer must stand aside, never invent a trade."""
    analyzer = TradeAnalyzer()
    analyzer.client = None

    mdm = MarketDataManager()
    quote = mdm.get_quote("NIFTY 50")
    df = mdm.candles_data.get("NIFTY 50")

    signal = analyzer.analyze_market_setup("NIFTY 50", quote, df)
    assert signal["actionable"] is False
    assert signal["decision"] == "NO_TRADE"
    assert "signal_type" not in signal


def test_safety_guardrail_and_execution():
    executor = KiteTradingExecutor()
    executor.mode = "PAPER"

    fake_signal = {
        "symbol": "NIFTY 50",
        "instrument_to_trade": "NIFTY 24850 CE",
        "signal_type": "BUY_CALL",
        "direction": "BULLISH",
        "entry_price": 120.0,
        "stop_loss": 100.0,
        "target_1": 160.0,
        "target_2": 180.0,
        "risk_reward": "1:2.0",
        "confidence": 85,
        "verbal_pitch": "Buy call alert",
        "technical_rationale": "Breakout above VWAP",
    }

    # 1. AI creates proposal (PENDING_APPROVAL)
    proposal = executor.create_trade_proposal(fake_signal)
    proposal_id = proposal["proposal_id"]
    assert proposal["status"] == OrderStatus.PENDING_APPROVAL
    assert proposal["lot_size"] == 1
    assert len(executor.positions) == 0  # NOT executed yet! Safety guardrail verified.

    # 2. User confirms/approves trade
    res = executor.approve_trade(proposal_id)
    assert res is not None
    assert len(executor.positions) == 1

    pos = next(iter(executor.positions.values()))
    assert pos["instrument"] == "NIFTY 24850 CE"
    assert pos["quantity"] == 1
    assert pos["buy_price"] == 120.0

    # 3. Position closing
    close_res = executor.close_position(pos["position_id"])
    assert close_res["message"] == "Position closed successfully"
    assert len(executor.positions) == 0


def test_close_position_restored_from_db():
    """Verifies that if backend restarts and memory is cleared, positions in SQLite can still be closed."""
    import database
    from kite_executor import KiteTradingExecutor

    executor = KiteTradingExecutor()

    # Insert an open position directly into database
    test_pos = {
        "position_id": "POS-TEST-DB-1",
        "symbol": "NIFTY 50",
        "instrument": "NIFTY 50 ATM PE",
        "signal_type": "BUY_PUT",
        "quantity": 1,
        "buy_price": 115.0,
        "current_ltp": 115.0,
        "stop_loss": 98.0,
        "target_1": 140.0,
        "target_2": 160.0,
        "status": "OPEN",
        "mode": "PAPER",
        "opened_at": "12:00:00",
    }
    database.save_position(test_pos)

    # Simulate fresh executor with empty in-memory dictionary
    executor.positions.clear()
    assert "POS-TEST-DB-1" not in executor.positions

    # Attempt close_position - should query SQLite fallback, close it, and update DB
    res = executor.close_position("POS-TEST-DB-1")
    assert res["message"] == "Position closed successfully"
    assert res["position"]["status"] == "CLOSED"

    # Verify in SQLite
    db_record = database.get_position_by_id("POS-TEST-DB-1")
    assert db_record is not None
    assert db_record["status"] == "CLOSED"
    assert db_record["exit_price"] == 115.0
