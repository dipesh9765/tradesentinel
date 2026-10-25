"""
Package-level alias for the single configuration module (backend/config.py).

Keeping one Settings instance and one instruments.json avoids the two copies drifting apart.
"""

from config import (  # noqa: F401
    Settings,
    settings,
    load_instruments_data,
    get_watchlist_symbols,
    get_kite_instrument_map,
    get_instrument_lot_sizes,
    get_tradingsymbol_map,
    get_instrument_types,
    is_index_symbol,
)
