"""
Root re-export shim for GenPrompts - TradeSentinel.
Allows seamless access to AI prompt templates from root-level modules and analyzers.
"""

from app.core.prompts import (
    INTRADAY_MARKET_SETUP_PROMPT,
    MARKET_SENTIMENT_ANALYSIS_PROMPT,
    TRADE_EXPLANATION_PROMPT,
    GenPrompts,
    render_prompt,
)

__all__ = [
    "INTRADAY_MARKET_SETUP_PROMPT",
    "MARKET_SENTIMENT_ANALYSIS_PROMPT",
    "TRADE_EXPLANATION_PROMPT",
    "GenPrompts",
    "render_prompt",
]
