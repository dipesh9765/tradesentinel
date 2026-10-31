"""
Trade Signal Validation - TradeSentinel

Pure, side-effect-free sanity checks applied to every trade signal before it can
become a proposal. Whatever produced the signal (quant rules or an LLM), these
checks guarantee the price levels are internally consistent and meet the minimum
risk-reward, so a malformed signal can never reach the broker.
"""

import re
from typing import Any

MIN_RISK_REWARD = 1.8
MAX_STOP_DISTANCE_PCT = 25.0  # Stop further than this from entry is not a "tight" stop
LONG_SIGNALS = ("BUY_CALL", "BUY_PUT", "BUY_EQUITY")
SHORT_SIGNALS = ("SHORT_EQUITY",)


def is_option_instrument(instrument: str) -> bool:
    """True for option labels such as 'BANKNIFTY 52000 CE' (not equities like RELIANCE)."""
    return bool(re.search(r"\s(CE|PE)\s*$", instrument or ""))


def compute_risk_reward(signal: dict[str, Any]) -> float | None:
    """Returns reward/risk for target_1, or None if the levels are unusable."""
    try:
        entry = float(signal["entry_price"])
        stop = float(signal["stop_loss"])
        target = float(signal["target_1"])
    except (KeyError, TypeError, ValueError):
        return None
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    return abs(target - entry) / risk


def validate_signal(signal: dict[str, Any], min_rr: float = MIN_RISK_REWARD) -> list[str]:
    """
    Returns a list of human-readable problems with the signal; empty means valid.

    Long-side signals (calls, puts and equity buys are all bought instruments)
    need stop < entry < target_1 <= target_2. Short equity mirrors that.
    """
    errors: list[str] = []

    signal_type = str(signal.get("signal_type", ""))
    if signal_type not in LONG_SIGNALS + SHORT_SIGNALS:
        return [f"Unknown signal type '{signal_type}'."]

    try:
        entry = float(signal["entry_price"])
        stop = float(signal["stop_loss"])
        t1 = float(signal["target_1"])
        t2 = float(signal.get("target_2", t1))
    except (KeyError, TypeError, ValueError):
        return ["Entry, stop-loss and target prices must all be present and numeric."]

    if min(entry, stop, t1, t2) <= 0:
        return ["All price levels must be positive."]

    if signal_type in LONG_SIGNALS:
        if not (stop < entry < t1):
            errors.append(f"Long setup needs stop ({stop}) < entry ({entry}) < target_1 ({t1}).")
        if t2 < t1:
            errors.append(f"target_2 ({t2}) must not be below target_1 ({t1}).")
    else:
        if not (stop > entry > t1):
            errors.append(f"Short setup needs stop ({stop}) > entry ({entry}) > target_1 ({t1}).")
        if t2 > t1:
            errors.append(f"target_2 ({t2}) must not be above target_1 ({t1}).")

    if errors:
        return errors

    stop_distance_pct = abs(entry - stop) / entry * 100.0
    if stop_distance_pct > MAX_STOP_DISTANCE_PCT:
        errors.append(f"Stop-loss is {stop_distance_pct:.1f}% from entry (max {MAX_STOP_DISTANCE_PCT:.0f}%).")

    rr = compute_risk_reward(signal)
    if rr is None or rr < min_rr:
        shown = "n/a" if rr is None else f"{rr:.2f}"
        errors.append(f"Risk-reward {shown} is below the minimum of {min_rr}.")

    return errors
