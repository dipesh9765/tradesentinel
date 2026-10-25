import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

from genConsts import GenConsts

load_dotenv()

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
INSTRUMENTS_FILE = BASE_DIR / GenConsts.INSTRUMENTS_FILE_NAME


def load_instruments_data(file_path: Path = INSTRUMENTS_FILE) -> List[Dict[str, Any]]:
    """Loads trading instruments metadata from external JSON configuration."""
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("instruments", [])
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")
    return []


def get_watchlist_symbols() -> List[str]:
    """Returns active symbol names from instruments.json."""
    instruments = load_instruments_data()
    return [i["symbol"] for i in instruments if i.get("enabled", True)]


def get_kite_instrument_map() -> Dict[str, str]:
    """Returns mapping of symbol name -> Kite exchange symbol (e.g. 'NSE:NIFTY 50')."""
    instruments = load_instruments_data()
    return {i["symbol"]: i["kite_symbol"] for i in instruments if i.get("enabled", True)}


def get_instrument_lot_sizes() -> Dict[str, int]:
    """Returns standard lot sizes per symbol from instruments.json."""
    instruments = load_instruments_data()
    return {i["symbol"]: i.get("lot_size", 1) for i in instruments if i.get("enabled", True)}


def get_tradingsymbol_map() -> Dict[str, str]:
    """Returns mapping of display symbol -> broker order tradingsymbol."""
    instruments = load_instruments_data()
    return {i["symbol"]: i.get("tradingsymbol", i["symbol"]) for i in instruments}


def get_instrument_types() -> Dict[str, str]:
    """Returns mapping of symbol name -> instrument type ('INDEX' or 'EQUITY')."""
    instruments = load_instruments_data()
    return {i["symbol"]: i.get("type", GenConsts.TYPE_EQUITY) for i in instruments}


def is_index_symbol(symbol: str) -> bool:
    """Dynamically checks if a symbol is classified as an INDEX from instruments.json."""
    types = get_instrument_types()
    return types.get(symbol, "").upper() == GenConsts.TYPE_INDEX


class Settings(BaseSettings):
    APP_NAME: str = GenConsts.APP_NAME
    APP_VERSION: str = GenConsts.APP_VERSION
    
    # Zerodha Kite Connect Settings
    KITE_API_KEY: str = os.getenv("KITE_API_KEY", "")
    KITE_API_SECRET: str = os.getenv("KITE_API_SECRET", "")
    KITE_ACCESS_TOKEN: str = os.getenv("KITE_ACCESS_TOKEN", "")
    KITE_REQUEST_TOKEN: str = os.getenv("KITE_REQUEST_TOKEN", "")
    
    # Gemini AI Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    
    # Trading Safety Parameters
    # As requested: "For intial phase to test, keep the lot size to 1"
    DEFAULT_LOT_SIZE: int = GenConsts.DEFAULT_LOT_SIZE
    MAX_LOT_SIZE: int = GenConsts.MAX_LOT_SIZE  # Safety guardrail for initial phase
    MAX_DAILY_LOSS: float = float(os.getenv("MAX_DAILY_LOSS", "2000"))  # Circuit breaker, in INR
    MAX_TRADES_PER_DAY: int = int(os.getenv("MAX_TRADES_PER_DAY", "5"))
    MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
    LOSS_STREAK_PAUSE_MINUTES: int = int(os.getenv("LOSS_STREAK_PAUSE_MINUTES", "60"))
    TRADING_MODE: str = os.getenv("TRADING_MODE", GenConsts.MODE_PAPER)  # "PAPER" or "LIVE"
    DEFAULT_PRODUCT: str = GenConsts.DEFAULT_PRODUCT  # Intraday
    INITIAL_PAPER_CAPITAL: float = GenConsts.INITIAL_PAPER_CAPITAL  # ₹1,00,000 for paper testing
    
    # Dynamic Intraday Trading Instruments loaded from instruments.json
    WATCHLIST_SYMBOLS: list[str] = get_watchlist_symbols()

settings = Settings()
