"""Typed contract shared by the UnifiedTradingEngine mixins.

The engine is split into cohesive mixins (risk, broker session, reconciliation, monitoring).
They all operate on the same portfolio state, so that state and the cross-mixin calls are
declared once here for static type checking. Nothing in this class runs at import time.
"""

import datetime
import threading
from typing import TYPE_CHECKING, Any

from app.trading.kite_broker import KiteExecutionEngine
from app.trading.paper_executor import PaperExecutionEngine


class EngineState:
    mode: str
    api_key: str
    api_secret: str
    access_token: str

    paper_engine: PaperExecutionEngine
    kite_engine: KiteExecutionEngine

    positions: dict[str, dict[str, Any]]
    orders_history: list[dict[str, Any]]
    pending_proposals: dict[str, dict[str, Any]]
    last_loss_times: dict[str, datetime.datetime]
    _last_kite_margins: dict[str, Any] | None
    _lock: threading.RLock

    MAX_ENTRY_DRIFT_PCT_EQUITY: float
    MAX_ENTRY_DRIFT_PCT_OPTION: float

    if TYPE_CHECKING:
        paper_balance: float

        def close_position(self, position_id: str, reason: str = ...) -> dict[str, Any]: ...
        def _finalize_close(self, pos: dict[str, Any], exit_price: float, reason: str) -> dict[str, Any]: ...
        def sync_live_kite_positions(self) -> set: ...
        def is_authenticated(self) -> bool: ...
        def verify_outgoing_kite_request(self) -> bool: ...
        @property
        def kite_client(self) -> Any: ...
