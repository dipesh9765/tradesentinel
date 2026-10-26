"""
Core Architecture Interfaces - TradeSentinel

This module defines the foundational abstract base classes (ABCs) and domain contracts
for the entire trading platform. By adhering to the Dependency Inversion Principle (DIP)
and Strategy Pattern, all execution engines (Paper Simulation, Zerodha KiteConnect, etc.),
market data providers, and quantitative AI analyzers implement these contracts, ensuring
clean separation of concerns, high testability, and enterprise extensibility.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd

from genConsts import GenConsts


class OrderStatus:
    """Standardized lifecycle states for trading orders and proposals."""

    PENDING_APPROVAL = GenConsts.STATUS_PENDING_APPROVAL
    APPROVED = "APPROVED"
    EXECUTED = GenConsts.STATUS_EXECUTED
    REJECTED = GenConsts.STATUS_REJECTED
    CANCELLED = GenConsts.STATUS_CANCELLED
    TRIGGERED_SL = "TRIGGERED_SL"
    TRIGGERED_TARGET = "TRIGGERED_TARGET"


class TradingMode(str, Enum):
    """Operational mode of the trading engine."""

    PAPER = GenConsts.MODE_PAPER
    LIVE = GenConsts.MODE_LIVE


@dataclass
class ExecutionResult:
    """
    Encapsulates the standardized outcome of an order execution attempt.

    Attributes:
        success (bool): Whether the broker or simulation engine accepted the order.
        order_id (str): Unique order identifier assigned by broker or simulator.
        instrument (str): Tradingsymbol executed (e.g., 'NIFTY 24850 CE' or 'RELIANCE').
        transaction_type (str): 'BUY' or 'SELL'.
        quantity (int): Number of lots or units executed.
        price (float): Average filled execution price.
        status (str): Current status string from broker or simulator.
        mode (str): Execution mode ('PAPER' or 'LIVE').
        message (str): Human-readable status message or rejection rationale.
        raw_response (Optional[Dict[str, Any]]): Unaltered broker response payload.
    """

    success: bool
    order_id: str
    instrument: str
    transaction_type: str
    quantity: int
    price: float
    status: str
    mode: str
    message: str
    raw_response: dict[str, Any] | None = None


class BaseOrderExecutor(ABC):
    """
    Abstract Base Class for order execution engines.

    Any broker integration (Zerodha Kite, Angel One, Interactive Brokers) or
    virtual simulation engine must implement this contract to seamlessly plug into
    the TradeSentinel trade orchestrator.
    """

    @property
    @abstractmethod
    def mode(self) -> str:
        """Returns the trading mode ('PAPER' or 'LIVE')."""
        pass

    @abstractmethod
    def execute_order(self, proposal: dict[str, Any], lot_size: int) -> dict[str, Any]:
        """
        Executes an approved trade proposal on the target broker or simulator.

        Args:
            proposal: Dictionary containing trade parameters (symbol, instrument,
                      signal_type, entry_price, stop_loss, targets, etc.).
            lot_size: Number of lots/quantity to trade.

        Returns:
            Dictionary containing order record, position details, and execution message.

        Raises:
            PermissionError: If authentication or risk checks fail.
            ValueError: If order parameters are invalid.
            RuntimeError: If broker order routing fails.
        """
        pass

    @abstractmethod
    def close_position(self, position_id: str, reason: str = "MANUAL_EXIT") -> dict[str, Any]:
        """
        Closes an open position by routing an offsetting order to the broker/simulator.

        Args:
            position_id: Unique position identifier.
            reason: Explanation for closure ('MANUAL_EXIT', 'TRIGGERED_SL', 'TRIGGERED_TARGET').

        Returns:
            Dictionary containing closed position details and realized P&L.
        """
        pass

    @abstractmethod
    def verify_session(self) -> dict[str, Any]:
        """
        Validates authentication and connectivity with the execution backend.

        Returns:
            Dictionary with 'valid' (bool), 'error' (Optional[str]), and 'timestamp' (float).
        """
        pass


class BaseMarketDataProvider(ABC):
    """
    Abstract Base Class for market data providers.

    Decouples market quote ingestion and historical candle streaming from the
    rest of the application. Allows swapping between Zerodha WebSocket/REST,
    Yahoo Finance, AlphaVantage, or mock replayers.
    """

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if the provider credentials and session are ready."""
        pass

    @abstractmethod
    def refresh_live_quotes(self) -> bool:
        """
        Synchronously fetches the latest top-of-book market quotes for all watched symbols.

        Returns:
            True if quotes were refreshed successfully, False otherwise.
        """
        pass

    @abstractmethod
    def get_quote(self, symbol: str) -> dict[str, Any]:
        """
        Retrieves current cached quote and option chain derivatives for a symbol.

        Args:
            symbol: Underlying instrument symbol (e.g. 'NIFTY 50').

        Returns:
            Quote dictionary with LTP, net change, OHLC, and ATM options.
        """
        pass

    @abstractmethod
    def get_candles(self, symbol: str, interval: str = "5minute", limit: int = 50) -> list[dict[str, Any]]:
        """
        Retrieves historical OHLCV candle bars enriched with technical indicators.

        Args:
            symbol: Underlying instrument symbol.
            interval: Bar timeframe ('minute', '5minute', 'day').
            limit: Number of candle records to return.

        Returns:
            List of candle dictionaries with technical indicator metrics.
        """
        pass


class BaseTradeAnalyzer(ABC):
    """
    Abstract Base Class for quantitative trade signal generators.

    Enables pluggable analytical models (Gemini Flash LLM, Deep Learning,
    Mean-Reversion, Momentum Cross, or Statistical Arbitrage algorithms).
    """

    @abstractmethod
    def analyze_market_setup(
        self, symbol: str, quote: dict[str, Any], candle_df: pd.DataFrame | None
    ) -> dict[str, Any]:
        """
        Analyzes live market metrics, indicator trends, and option chains
        to produce a high-probability trade proposal.

        Args:
            symbol: Ticker symbol being scanned.
            quote: Current live market quote and derivative pricing.
            candle_df: Historical OHLCV DataFrame enriched with technical indicators.

        Returns:
            Dictionary formatted according to TradeProposal schema.
        """
        pass


class BaseNotificationDispatcher(ABC):
    """
    Abstract Base Class for multi-channel alerting services.

    Dispatches critical trading signals and order lifecycle events across
    chat applications (Telegram, Discord, Slack) and desktop operating systems.
    """

    @abstractmethod
    async def notify_trade_proposal(self, proposal: dict[str, Any]) -> dict[str, Any]:
        """Dispatches notification when a new AI trade proposal is generated."""
        pass

    @abstractmethod
    async def notify_trade_executed(self, order: dict[str, Any], position: dict[str, Any]) -> None:
        """Dispatches notification when an order is filled on broker/simulator."""
        pass

    @abstractmethod
    async def notify_target_or_sl(self, symbol: str, reason: str, pnl: float) -> None:
        """Dispatches alert when stop-loss or profit target is triggered."""
        pass
