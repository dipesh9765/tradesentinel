"""
Centralized AI Prompt Templates - TradeSentinel.
Eliminates hardcoded prompts in application logic.
All dynamic placeholders follow the format '%KEY%' and are replaced at runtime.
"""

from typing import Dict, Any


# 1. Primary Intraday Quantitative Trading Setup Prompt (Multi-Factor Institutional)
INTRADAY_MARKET_SETUP_PROMPT = """
You are an elite institutional intraday quantitative trading strategist and chief risk officer specializing in the Indian stock and derivatives market (NSE Zerodha).
Analyze the following live multi-factor quantitative setup for %SYMBOL%:

--- MARKET DATA & MULTI-FACTOR INDICATORS ---
- Current Price (LTP): ₹%CLOSE%
- EMA Ribbon: EMA 9 = ₹%EMA_9% | EMA 21 = ₹%EMA_21% | EMA 50 = ₹%EMA_50%
- Institutional Baseline: VWAP = ₹%VWAP% (Upper Band = ₹%VWAP_UPPER%, Lower Band = ₹%VWAP_LOWER%)
- Trend & Volatility: Supertrend (10,3) = ₹%SUPERTREND% (%SUPERTREND_DIR%) | ATR (14) = ₹%ATR%
- Trend Strength: ADX (14) = %ADX% (+DI = %PLUS_DI%, -DI = %MINUS_DI%)
- Momentum Oscillator: RSI (14) = %RSI% (Regime: %RSI_REGIME%)
- Indian Key Levels (CPR): Pivot = ₹%PIVOT% | Top Central (TC) = ₹%TC% | Bottom Central (BC) = ₹%BC% (%CPR_REGIME%)
- Floor S/R Levels: Resistance 1 (R1) = ₹%R1% | Support 1 (S1) = ₹%S1%
- Option Derivatives: Call Option Quote = %CALL_OPTION% | Put Option Quote = %PUT_OPTION%
- Quantitative Engine Pre-Assessment: Confluence Score = %CONFLUENCE_SCORE%/100 | Direction = %QUANT_DIRECTION%
- Algorithmic Factor Findings: %FACTOR_FINDINGS%

--- DECISION & EXECUTION RULES ---
1. Evaluate whether a high-conviction, asymmetric risk-to-reward trade exists:
   - BULLISH TRADE: Requires Price > VWAP, Supertrend GREEN, EMA9 > EMA21, ADX >= 20, and RSI > 50. Recommend ATM/Slight ITM Call Option Buy (for Indices) or Intraday Long MIS (for Equities).
   - BEARISH TRADE: Requires Price < VWAP, Supertrend RED, EMA9 < EMA21, ADX >= 20, and RSI < 50. Recommend ATM/Slight ITM Put Option Buy (for Indices) or Intraday Short MIS (for Equities).
2. Risk-Reward Mandate:
   - Calculate a strict, tight Stop-Loss based on Supertrend/ATR/Pivots and Target levels with AT LEAST 1:1.8 Risk-to-Reward ratio (Target 1) and extended Target 2 (1:2.5+ R:R).
   - Lot size MUST be exactly 1.
3. Rationale:
   - Provide institutional technical rationale detailing EMA alignment, VWAP support/resistance, CPR width, and ADX momentum.
"""

# 2. General Market Sentiment & Sector Overview Prompt
MARKET_SENTIMENT_ANALYSIS_PROMPT = """
You are an institutional macro quantitative analyst reviewing live market conditions on NSE.
Analyze overall momentum across:
- Market Trend: %MARKET_TREND%
- Advance / Decline Ratio: %ADVANCE_DECLINE%
- VIX Level: %INDIA_VIX%
- Primary Sector Movers: %SECTOR_MOVERS%

Provide concise risk warnings and institutional bias for intraday scalping.
"""


def render_prompt(template: str, **replacements: Any) -> str:
    """
    Renders a prompt template by dynamically substituting '%KEY%' placeholders with runtime values.
    
    Supports case-insensitive placeholder keys (e.g. symbol='NIFTY' replaces both '%SYMBOL%' and '%symbol%').
    
    Args:
        template: The prompt string containing '%KEY%' placeholders.
        **replacements: Keyword arguments representing key-value pairs to replace.
        
    Returns:
        Rendered prompt string ready to be passed to the Gemini model.
    """
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(f"%{key.upper()}%", str(value))
        rendered = rendered.replace(f"%{key}%", str(value))
    return rendered.strip()


class GenPrompts:
    """Namespace container for all system prompt templates and renderer."""
    INTRADAY_MARKET_SETUP = INTRADAY_MARKET_SETUP_PROMPT
    MARKET_SENTIMENT_ANALYSIS = MARKET_SENTIMENT_ANALYSIS_PROMPT
    render = staticmethod(render_prompt)


# 3. Trade Explanation Prompt (levels are fixed by the quant engine; the LLM only explains)
TRADE_EXPLANATION_PROMPT = """
You are an intraday trading desk analyst on the Indian market (NSE). A rules-based engine has ALREADY decided the trade and fixed every price level. You must NOT change or suggest different levels. Your job is to explain it clearly.

Trade: %ACTION% %INSTRUMENT% (underlying %SYMBOL%, LTP ₹%CLOSE%)
Entry ₹%ENTRY% | Stop-Loss ₹%STOP_LOSS% | Target 1 ₹%TARGET_1% | Target 2 ₹%TARGET_2%
Engine confluence score: %CONFLUENCE_SCORE%/100
Engine findings: %FACTOR_FINDINGS%

Reply with ONLY a JSON object with exactly these string keys:
- "verbal_pitch": 1-2 spoken sentences stating the trade, entry, stop-loss and target, ending by asking the user to say 'Approve' to confirm.
- "technical_rationale": 2-4 sentences explaining why the setup qualifies and the main risk that would invalidate it. Use only the findings given; do not invent data.
"""


GenPrompts.TRADE_EXPLANATION = TRADE_EXPLANATION_PROMPT
