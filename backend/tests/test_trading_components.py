"""Unit tests for the engine components split out of the former kite_executor module."""

import datetime

import pytest

from app.core.config import settings
from app.db import database
from app.market.market_data import market_data_manager
from app.trading.engine import UnifiedTradingEngine
from app.trading.kite_broker import KiteExecutionEngine
from app.trading.monitor import PositionMonitorMixin
from app.trading.reconciliation import ReconciliationMixin
from app.trading.risk import RiskMixin
from app.trading.session import BrokerSessionMixin

NOW = datetime.datetime.now()


@pytest.fixture
def engine(monkeypatch):
    # conftest relaxes the discipline limits for the wider suite; pin realistic values here.
    monkeypatch.setattr(settings, "MAX_TRADES_PER_DAY", 5)
    monkeypatch.setattr(settings, "MAX_CONSECUTIVE_LOSSES", 3)
    monkeypatch.setattr(settings, "LOSS_STREAK_PAUSE_MINUTES", 60)
    eng = UnifiedTradingEngine()
    eng.mode = "PAPER"
    eng.positions.clear()
    return eng


def _closed(pnl: float, minutes_ago: int = 1) -> dict:
    ts = (NOW - datetime.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")
    return {"position_id": "p", "realized_pnl": pnl, "closed_at": ts}


def test_engine_is_composed_of_the_expected_components():
    mro = UnifiedTradingEngine.__mro__
    for mixin in (RiskMixin, BrokerSessionMixin, ReconciliationMixin, PositionMonitorMixin):
        assert mixin in mro
    assert isinstance(UnifiedTradingEngine().kite_engine, KiteExecutionEngine)


def test_daily_trade_cap_blocks_new_entries(engine, monkeypatch):
    rows = [_closed(100.0) for _ in range(settings.MAX_TRADES_PER_DAY)]
    monkeypatch.setattr(database, "get_closed_positions_on", lambda d, m: rows)
    with pytest.raises(ValueError, match="Daily trade limit"):
        engine._check_trading_limits()


def test_loss_streak_pauses_trading_then_resumes(engine, monkeypatch):
    streak = settings.MAX_CONSECUTIVE_LOSSES
    recent = [_closed(-50.0, minutes_ago=5) for _ in range(streak)]
    monkeypatch.setattr(database, "get_closed_positions_on", lambda d, m: recent)
    with pytest.raises(ValueError, match="paused after"):
        engine._check_trading_limits()

    stale = [_closed(-50.0, minutes_ago=settings.LOSS_STREAK_PAUSE_MINUTES + 30) for _ in range(streak)]
    monkeypatch.setattr(database, "get_closed_positions_on", lambda d, m: stale)
    engine._check_trading_limits()  # pause elapsed: allowed


def test_a_win_breaks_the_loss_streak(engine, monkeypatch):
    rows = [_closed(200.0, 2)] + [_closed(-50.0, 5) for _ in range(settings.MAX_CONSECUTIVE_LOSSES)]
    monkeypatch.setattr(database, "get_closed_positions_on", lambda d, m: rows)
    engine._check_trading_limits()


@pytest.mark.parametrize(("ltp", "blocked"), [(100.4, False), (102.0, True), (97.0, True)])
def test_equity_entry_drift_guard(engine, monkeypatch, ltp, blocked):
    monkeypatch.setattr(market_data_manager, "get_quote", lambda s: {"ltp": ltp})
    proposal = {"entry_price": 100.0, "instrument": "RELIANCE", "symbol": "RELIANCE"}
    if blocked:
        with pytest.raises(ValueError, match="Slippage guard"):
            engine._check_entry_drift(proposal)
    else:
        engine._check_entry_drift(proposal)


def test_live_mode_fails_closed_when_price_is_unknown(engine, monkeypatch):
    engine.mode = "LIVE"
    monkeypatch.setattr(engine.kite_engine, "get_option_ltp", lambda label: None)
    proposal = {"entry_price": 100.0, "instrument": "NIFTY 24850 CE", "symbol": "NIFTY 50"}
    with pytest.raises(ValueError, match="trade blocked for safety"):
        engine._check_entry_drift(proposal)


def test_paper_mode_skips_option_drift_check(engine):
    proposal = {"entry_price": 100.0, "instrument": "NIFTY 24850 CE", "symbol": "NIFTY 50"}
    engine._check_entry_drift(proposal)  # no option quotes in paper mode: must not raise


def test_portfolio_summary_aggregates_pnl(engine):
    engine.orders_history = [{"pnl": 120.0}, {"pnl": -20.0}, {"status": "OPEN"}]
    engine.positions = {"a": {"unrealized_pnl": 30.5}, "b": {"unrealized_pnl": -10.25}}
    summary = engine.get_portfolio_summary()
    assert summary["realized_pnl"] == 100.0
    assert summary["unrealized_pnl"] == 20.25
    assert summary["total_pnl"] == 120.25
    assert summary["open_positions_count"] == 2
    assert summary["completed_orders_count"] == 3
