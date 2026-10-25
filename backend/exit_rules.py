"""
Position Exit Rules - TradeSentinel

Pure stop-loss / target / trailing logic shared by the live trading engine and the backtester,
so the strategy that is backtested is exactly the one that trades.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

BREAK_EVEN_TRIGGER_PCT = 6.0
T1_PROFIT_LOCK_FRACTION = 0.5


def check_exit_triggers(pos: Dict[str, Any], cur_price: float) -> Optional[str]:
    """
    Evaluates whether a position has reached its Stop-Loss or Target threshold and applies the
    multi-tier trailing stop (mutating pos["stop_loss"]):
        - Tier 1: at +6% gain, trail the stop to cost (break-even).
        - Tier 2: when Target 1 is reached, lock in 50% of the Target 1 profit.
        - Tier 3: Target 2 reached -> full exit.

    Returns:
        'STOP_LOSS_HIT', 'TARGET_HIT', or None.
    """
    is_long = "BUY" in pos["signal_type"]
    sl = float(pos["stop_loss"])
    t1 = float(pos["target_1"])
    t2 = float(pos.get("target_2", t1 * 1.05))
    buy_price = float(pos["buy_price"])

    gain_pct = ((cur_price - buy_price) / buy_price) * 100 if is_long else ((buy_price - cur_price) / buy_price) * 100

    if is_long:
        if gain_pct >= BREAK_EVEN_TRIGGER_PCT and sl < buy_price:
            pos["stop_loss"] = buy_price
            logger.info(f"Position {pos.get('position_id')}: +{gain_pct:.1f}% gain! SL trailed to Break-Even ₹{buy_price}")

        if cur_price >= t1:
            locked_gain_sl = round(buy_price + ((t1 - buy_price) * T1_PROFIT_LOCK_FRACTION), 2)
            if pos["stop_loss"] < locked_gain_sl:
                pos["stop_loss"] = locked_gain_sl
                logger.info(f"Position {pos.get('position_id')}: Target 1 hit! Trailing SL to locked profit ₹{locked_gain_sl}")

        if cur_price <= pos["stop_loss"]:
            return "STOP_LOSS_HIT"
        if cur_price >= t2:
            return "TARGET_HIT"
    else:
        if gain_pct >= BREAK_EVEN_TRIGGER_PCT and sl > buy_price:
            pos["stop_loss"] = buy_price
            logger.info(f"Position {pos.get('position_id')}: +{gain_pct:.1f}% gain! SL trailed to Break-Even ₹{buy_price}")

        if cur_price <= t1:
            locked_gain_sl = round(buy_price - ((buy_price - t1) * T1_PROFIT_LOCK_FRACTION), 2)
            if pos["stop_loss"] > locked_gain_sl:
                pos["stop_loss"] = locked_gain_sl
                logger.info(f"Position {pos.get('position_id')}: Target 1 hit! Trailing SL to locked profit ₹{locked_gain_sl}")

        if cur_price >= pos["stop_loss"]:
            return "STOP_LOSS_HIT"
        if cur_price <= t2:
            return "TARGET_HIT"

    return None
