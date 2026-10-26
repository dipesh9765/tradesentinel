"""
Unit Tests for Autonomous Market Opportunity Scanner - TradeSentinel
"""

import datetime

import pytest

from app.market.scanner import OpportunityScannerService
from app.trading.kite_executor import kite_executor


@pytest.fixture
def scanner():
    """Returns a fresh instance of OpportunityScannerService for testing."""
    return OpportunityScannerService(scan_interval_sec=5.0, cooldown_minutes=10)


def test_scanner_cooldown_logic(scanner):
    """Verifies that alerted symbols enter a 10-minute cooldown."""
    symbol = "NIFTY 50"
    assert scanner.is_on_cooldown(symbol) is False

    # Mark symbol as alerted
    scanner.last_alert_times[symbol] = datetime.datetime.now()
    assert scanner.is_on_cooldown(symbol) is True

    # After cooldown expires (simulate past timestamp)
    scanner.last_alert_times[symbol] = datetime.datetime.now() - datetime.timedelta(minutes=15)
    assert scanner.is_on_cooldown(symbol) is False


def test_scanner_skips_when_position_open(scanner):
    """Verifies that scanner skips symbols that already have an open active position."""
    symbol = "BANK NIFTY"
    pos = {
        "position_id": "POS-AUTO-1",
        "symbol": symbol,
        "status": "OPEN",
        "instrument": "BANKNIFTY 51200 CE",
    }
    kite_executor.positions["POS-AUTO-1"] = pos

    # In single scan, should return None due to active position
    import asyncio

    res = asyncio.run(scanner.scan_single_symbol(symbol))
    assert res is None

    # Cleanup
    kite_executor.positions.pop("POS-AUTO-1", None)


def test_scanner_start_stop(scanner):
    """Verifies scanner service state transitions."""
    assert scanner.is_running is False
    scanner.is_running = True
    assert scanner.is_running is True
    scanner.stop()
    assert scanner.is_running is False
