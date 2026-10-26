"""
Package-level alias for the single configuration module (backend/config.py).

Keeping one Settings instance and one instruments.json avoids the two copies drifting apart.
"""

from config import (
    Settings,
    get_instrument_lot_sizes,
    get_instrument_types,
    get_kite_instrument_map,
    get_tradingsymbol_map,
    get_watchlist_symbols,
    is_index_symbol,
    load_instruments_data,
    settings,
)
