"""
TradeSentinel - Core Architecture Layer
Provides abstract interfaces and contract definitions for execution engines,
market data providers, quantitative strategy analyzers, and notification channels.
"""

from .interfaces import (
    BaseMarketDataProvider,
    BaseNotificationDispatcher,
    BaseOrderExecutor,
    BaseTradeAnalyzer,
    ExecutionResult,
    OrderStatus,
    TradingMode,
)

__all__ = [
    "BaseMarketDataProvider",
    "BaseNotificationDispatcher",
    "BaseOrderExecutor",
    "BaseTradeAnalyzer",
    "ExecutionResult",
    "OrderStatus",
    "TradingMode",
]
