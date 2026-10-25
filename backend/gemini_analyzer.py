"""
Trade Analysis Engine - KitePulse AI

The deterministic quantitative rules engine is the ONLY source of trade decisions and price
levels (entry, stop-loss, targets). The configured LLM (Gemini, OpenAI or Claude, chosen in
Settings) is used purely to explain the trade in natural language. It cannot create a trade the
rules rejected, and it cannot move any price level.

Every signal also passes through trade_validation before it leaves this module.
"""

import re
import logging
from typing import Dict, Any, Optional

import pandas as pd

import ai_providers
from prompts import render_prompt, TRADE_EXPLANATION_PROMPT
from core.interfaces import BaseTradeAnalyzer
from quant_strategy import quant_engine
from trade_validation import validate_signal

logger = logging.getLogger(__name__)

ACTION_WORDS = {
    "BUY_CALL": "BUY CALL", "BUY_PUT": "BUY PUT",
    "BUY_EQUITY": "LONG", "SHORT_EQUITY": "SHORT",
}


def _numbers_in(text: str) -> list:
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*\.?\d*", text or "")]


def _pitch_matches_levels(pitch: str, signal: Dict[str, Any]) -> bool:
    """True only if the spoken pitch quotes the real entry and stop-loss."""
    nums = _numbers_in(pitch)
    for level in (signal["entry_price"], signal["stop_loss"]):
        if not any(abs(n - float(level)) < 0.011 for n in nums):
            return False
    return True


class GeminiMarketAnalyzer(BaseTradeAnalyzer):
    """
    Quant-gated analyzer. Name kept for backward compatibility; the LLM provider is
    selected at runtime through ai_providers (Gemini, OpenAI or Anthropic).
    """

    def __init__(self):
        self._ai_disabled = False

    # ------------------------------------------------------------------ AI status

    @property
    def client(self):
        """Truthy when the active provider has an API key (kept for existing callers)."""
        if self._ai_disabled:
            return None
        try:
            return True if ai_providers.is_configured() else None
        except Exception:
            return None

    @client.setter
    def client(self, value) -> None:
        self._ai_disabled = value is None

    def load_credentials(self) -> None:
        """Credentials are read from the vault on every call; nothing to reload."""

    def update_api_key(self, key: str) -> None:
        """Backward-compatible helper: stores a Gemini key."""
        ai_providers.set_api_key("gemini", key)

    # ------------------------------------------------------------------ analysis

    def analyze_market_setup(
        self,
        symbol: str,
        quote: Dict[str, Any],
        candle_df: Optional[pd.DataFrame]
    ) -> Dict[str, Any]:
        """
        Returns an actionable signal dict (actionable=True) or a NO_TRADE dict
        (actionable=False). Callers must check the flag before creating a proposal.
        """
        quant = quant_engine.evaluate_quantitative_setup(symbol, quote, candle_df)
        if not quant.get("actionable"):
            return self._no_trade(symbol, quant.get("reason", "No qualifying setup."), quant)

        signal = {
            "symbol": quant["symbol"],
            "instrument_to_trade": quant["instrument_to_trade"],
            "signal_type": quant["signal_type"],
            "direction": quant["direction"],
            "lot_size": 1,
            "entry_price": quant["entry_price"],
            "stop_loss": quant["stop_loss"],
            "target_1": quant["target_1"],
            "target_2": quant["target_2"],
            "risk_reward": quant["risk_reward"],
            "confidence": quant["confidence"],
            "confluence_score": quant["confluence_score"],
            "verbal_pitch": quant["verbal_pitch"],
            "technical_rationale": quant["technical_rationale"],
            "ai_model": "Quant Rule Engine",
            "source": "Algorithmic Quant Rules",
            "actionable": True,
        }

        problems = validate_signal(signal)
        if problems:
            logger.warning(f"Signal for {symbol} rejected by validator: {problems}")
            return self._no_trade(symbol, "Signal failed validation: " + " ".join(problems), quant)

        if self.client:
            self._apply_ai_explanation(signal, quote, quant)
        return signal

    def _apply_ai_explanation(self, signal: Dict[str, Any], quote: Dict[str, Any], quant: Dict[str, Any]) -> None:
        """Replaces pitch/rationale text with the LLM's explanation. Never touches price levels."""
        provider = ai_providers.get_active_provider()
        model = ai_providers.get_model(provider)
        prompt = render_prompt(
            TRADE_EXPLANATION_PROMPT,
            action=ACTION_WORDS.get(signal["signal_type"], signal["signal_type"]),
            instrument=signal["instrument_to_trade"],
            symbol=signal["symbol"],
            close=f"{float(quote.get('ltp') or 0):.2f}",
            entry=signal["entry_price"],
            stop_loss=signal["stop_loss"],
            target_1=signal["target_1"],
            target_2=signal["target_2"],
            confluence_score=signal["confluence_score"],
            factor_findings=quant.get("technical_rationale", ""),
        )
        try:
            data = ai_providers.generate_json(prompt, provider=provider, model=model)
        except Exception as e:
            logger.warning(f"AI explanation unavailable ({provider}/{model}); using rule-engine text: {e}")
            return

        pitch = str(data.get("verbal_pitch", "")).strip()
        rationale = str(data.get("technical_rationale", "")).strip()
        if rationale:
            signal["technical_rationale"] = rationale
        if pitch and _pitch_matches_levels(pitch, signal):
            signal["verbal_pitch"] = pitch
        elif pitch:
            logger.warning("AI pitch quoted levels that differ from the engine's; keeping rule-engine pitch.")
        signal["ai_model"] = f"{provider}/{model}"
        signal["source"] = f"{ai_providers.PROVIDERS[provider]['label']} (explanation only)"

    @staticmethod
    def _no_trade(symbol: str, reason: str, quant: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "actionable": False,
            "decision": "NO_TRADE",
            "reason": reason,
            "confluence_score": quant.get("confluence_score", 0),
            "technical_rationale": quant.get("technical_rationale", ""),
            "source": "Algorithmic Quant Rules",
        }


# Singleton instance
gemini_analyzer = GeminiMarketAnalyzer()
