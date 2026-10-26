"""
Unit Tests for TradeSentinel Core Architecture Layer
Validates the abstract base classes, paper simulation engine, and strategy decoupling.
"""

from app.core.interfaces import BaseOrderExecutor, OrderStatus
from app.trading.kite_executor import KiteExecutionEngine
from app.trading.paper_executor import PaperExecutionEngine


def test_core_interfaces_inheritance():
    """Verifies that execution engines implement the BaseOrderExecutor contract."""
    paper = PaperExecutionEngine(initial_balance=50000.0)
    assert isinstance(paper, BaseOrderExecutor)
    assert paper.mode == "PAPER"
    assert paper.paper_balance == 50000.0

    kite_engine = KiteExecutionEngine()
    assert isinstance(kite_engine, BaseOrderExecutor)
    assert kite_engine.mode == "LIVE"


def test_paper_execution_engine_lifecycle():
    """Validates complete paper execution lifecycle: order fill, P&L tracking, and exit."""
    paper = PaperExecutionEngine(initial_balance=100000.0)
    verif = paper.verify_session()
    assert verif["valid"] is True
    assert verif["mode"] == "PAPER"

    proposal = {
        "proposal_id": "TEST1234",
        "symbol": "RELIANCE",
        "instrument": "RELIANCE MIS",
        "signal_type": "BUY_EQUITY",
        "direction": "BULLISH",
        "entry_price": 2500.0,
        "stop_loss": 2480.0,
        "target_1": 2540.0,
        "target_2": 2560.0,
    }

    # 1. Execute order
    res = paper.execute_order(proposal, lot_size=1)
    assert res["mode"] == "PAPER"
    assert "order" in res
    assert "position" in res
    pos_id = res["position"]["position_id"]
    assert pos_id in paper.positions

    # 2. Update price tick with profit
    paper.update_pnl({"RELIANCE": 2520.0})
    assert paper.positions[pos_id]["unrealized_pnl"] == 20.0
    assert paper.positions[pos_id]["current_ltp"] == 2520.0

    # 3. Close position manually
    close_res = paper.close_position(pos_id, reason="MANUAL_EXIT")
    assert close_res["message"] == "Position closed successfully"
    assert close_res["realized_pnl"] == 20.0
    assert paper.paper_balance == 100020.0
    assert len(paper.positions) == 0


def test_paper_execution_stop_loss_trigger():
    """Validates that update_pnl automatically terminates a position when stop-loss is hit."""
    paper = PaperExecutionEngine(initial_balance=100000.0)
    proposal = {
        "proposal_id": "SLTEST01",
        "symbol": "INFY",
        "instrument": "INFY MIS",
        "signal_type": "BUY_EQUITY",
        "direction": "BULLISH",
        "entry_price": 1800.0,
        "stop_loss": 1780.0,
        "target_1": 1840.0,
        "target_2": 1860.0,
    }

    res = paper.execute_order(proposal, lot_size=1)
    pos_id = res["position"]["position_id"]

    # Trigger stop loss breach (price drops to 1775 <= 1780)
    closed = paper.update_pnl({"INFY": 1775.0})
    assert len(closed) == 1
    assert closed[0]["reason"] == OrderStatus.TRIGGERED_SL
    assert pos_id not in paper.positions
