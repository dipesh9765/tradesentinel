"""
Unit test suite for centralized prompts and dynamic '%VALUE%' placeholder substitution.
"""

from app.core.prompts import INTRADAY_MARKET_SETUP_PROMPT, GenPrompts, render_prompt


def test_intraday_market_setup_prompt_placeholders():
    """Verifies that all '%KEY%' tokens in the intraday setup prompt are substituted at runtime."""
    rendered = render_prompt(
        INTRADAY_MARKET_SETUP_PROMPT,
        symbol="NIFTY 50",
        close=24850.50,
        ema_9=24820.10,
        ema_21=24790.00,
        ema_50=24750.00,
        vwap=24800.00,
        vwap_upper=24850.00,
        vwap_lower=24750.00,
        supertrend=24780.00,
        supertrend_dir="BULLISH",
        rsi=58.5,
        rsi_regime="Bullish Momentum",
        atr=45.2,
        adx=26.4,
        plus_di=28.0,
        minus_di=16.0,
        pivot=24800.00,
        tc=24830.00,
        bc=24770.00,
        cpr_regime="NARROW",
        r1=24900.00,
        s1=24700.00,
        call_option="NIFTY 24850 CE",
        put_option="NIFTY 24850 PE",
        confluence_score=85,
        quant_direction="BULLISH",
        factor_findings="Supertrend and EMA alignment",
    )

    # Check that placeholders were replaced
    assert "%SYMBOL%" not in rendered
    assert "%CLOSE%" not in rendered
    assert "%EMA_9%" not in rendered
    assert "%EMA_21%" not in rendered
    assert "%VWAP%" not in rendered
    assert "%RSI%" not in rendered
    assert "%ATR%" not in rendered
    assert "%CALL_OPTION%" not in rendered
    assert "%PUT_OPTION%" not in rendered

    # Check that actual values appear
    assert "NIFTY 50" in rendered
    assert "24850.5" in rendered
    assert "24820.1" in rendered
    assert "NIFTY 24850 CE" in rendered
    assert "NIFTY 24850 PE" in rendered


def test_market_sentiment_analysis_prompt():
    """Verifies macro sentiment prompt placeholder replacement."""
    rendered = GenPrompts.render(
        GenPrompts.MARKET_SENTIMENT_ANALYSIS,
        market_trend="BULLISH",
        advance_decline="32/18",
        india_vix=14.2,
        sector_movers="NIFTY AUTO, NIFTY IT",
    )

    assert "%MARKET_TREND%" not in rendered
    assert "%INDIA_VIX%" not in rendered
    assert "BULLISH" in rendered
    assert "14.2" in rendered
