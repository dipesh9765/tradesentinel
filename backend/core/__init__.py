"""
TradeSentinel - Core Architecture Layer
Provides abstract interfaces and contract definitions for execution engines,
market data providers, quantitative strategy analyzers, and notification channels.
"""

from .interfaces import (
    BaseOrderExecutor,
    BaseMarketDataProvider,
    BaseTradeAnalyzer,
    BaseNotificationDispatcher,
    OrderStatus,
    TradingMode,
    ExecutionResult
)

__all__ = [
    "BaseOrderExecutor",
    "BaseMarketDataProvider",
    "BaseTradeAnalyzer",
    "BaseNotificationDispatcher",
    "OrderStatus",
    "TradingMode",
    "ExecutionResult",
]
