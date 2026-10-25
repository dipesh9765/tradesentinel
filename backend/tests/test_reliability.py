"""
Reliability tests: signal validation, quant-gated analyzer, multi-provider AI layer,
and the LIVE execution lifecycle (fills, broker-side stop, real exits) against a fake Kite client.
"""

import datetime
import pytest

import ai_providers
from trade_validation import validate_signal, is_option_instrument
from gemini_analyzer import GeminiMarketAnalyzer
from kite_executor import KiteExecutionEngine, UnifiedTradingEngine


@pytest.fixture(autouse=True)
def _close_leftover_positions():
    """Live-execution tests persist positions; close them so other test modules start clean."""
    yield
    import database
    conn = database.get_db_connection()
    try:
        conn.execute("UPDATE positions SET status = 'CLOSED' WHERE status = 'OPEN'")
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- validation

def _signal(**over):
    base = {"signal_type": "BUY_CALL", "entry_price": 100.0, "stop_loss": 90.0, "target_1": 120.0, "target_2": 130.0}
    base.update(over)
    return base


def test_valid_long_signal_passes():
    assert validate_signal(_signal()) == []


@pytest.mark.parametrize("over", [
    {"stop_loss": 105.0},                       # stop above entry on a long
    {"target_1": 95.0},                         # target below entry
    {"target_1": 110.0, "target_2": 111.0},     # RR 1.0 < 1.8
    {"target_2": 115.0},                        # target_2 below target_1
    {"stop_loss": 0},                           # non-positive price
    {"stop_loss": 40.0, "target_1": 200.0, "target_2": 210.0},  # stop >25% away
])
def test_bad_long_signals_rejected(over):
    assert validate_signal(_signal(**over))


def test_short_signal_levels():
    ok = {"signal_type": "SHORT_EQUITY", "entry_price": 100.0, "stop_loss": 105.0, "target_1": 91.0, "target_2": 85.0}
    assert validate_signal(ok) == []
    assert validate_signal({**ok, "stop_loss": 95.0})


def test_option_detector_does_not_confuse_equities():
    assert is_option_instrument("BANKNIFTY 52000 CE")
    assert is_option_instrument("NIFTY 24850 PE")
    assert not is_option_instrument("RELIANCE MIS")
    assert not is_option_instrument("RELIANCE")


def test_create_proposal_rejects_invalid_signal():
    engine = UnifiedTradingEngine()
    engine.mode = "PAPER"
    bad = {
        "symbol": "NIFTY 50", "instrument_to_trade": "NIFTY 24850 CE", "signal_type": "BUY_CALL",
        "direction": "BULLISH", "entry_price": 120.0, "stop_loss": 130.0, "target_1": 150.0,
        "target_2": 170.0, "risk_reward": "1:2.0", "confidence": 80, "verbal_pitch": "x", "technical_rationale": "y",
    }
    with pytest.raises(ValueError):
        engine.create_trade_proposal(bad)


def test_expired_proposal_cannot_be_approved():
    engine = UnifiedTradingEngine()
    engine.mode = "PAPER"
    sig = {
        "symbol": "NIFTY 50", "instrument_to_trade": "NIFTY 24850 CE", "signal_type": "BUY_CALL",
        "direction": "BULLISH", "entry_price": 100.0, "stop_loss": 90.0, "target_1": 120.0,
        "target_2": 130.0, "risk_reward": "1:2.0", "confidence": 80, "verbal_pitch": "x", "technical_rationale": "y",
    }
    proposal = engine.create_trade_proposal(sig)
    proposal["created_ts"] -= 600
    with pytest.raises(ValueError, match="expired"):
        engine.approve_trade(proposal["proposal_id"])
    assert len(engine.positions) == 0


# --------------------------------------------------------------------------- analyzer

class _FakeQuant:
    def __init__(self, result):
        self.result = result

    def evaluate_quantitative_setup(self, *a, **k):
        return self.result


ACTIONABLE = {
    "symbol": "BANK NIFTY", "actionable": True, "instrument_to_trade": "BANKNIFTY 52000 CE",
    "signal_type": "BUY_CALL", "direction": "BULLISH", "entry_price": 200.0, "stop_loss": 180.0,
    "target_1": 240.0, "target_2": 260.0, "risk_reward": "1:2.0", "confidence": 85, "confluence_score": 85,
    "verbal_pitch": "Rule pitch: entry 200.0 stop 180.0", "technical_rationale": "rules rationale",
}


def test_analyzer_never_trades_when_quant_says_no(monkeypatch):
    import gemini_analyzer as ga
    monkeypatch.setattr(ga, "quant_engine", _FakeQuant({"actionable": False, "reason": "chop", "confluence_score": 40}))
    called = []
    monkeypatch.setattr(ai_providers, "generate_json", lambda *a, **k: called.append(1) or {})
    monkeypatch.setattr(ai_providers, "is_configured", lambda provider=None: True)
    out = GeminiMarketAnalyzer().analyze_market_setup("BANK NIFTY", {"ltp": 52000}, None)
    assert out["actionable"] is False
    assert not called  # LLM is never consulted for a rejected setup


def test_llm_cannot_move_price_levels(monkeypatch):
    import gemini_analyzer as ga
    monkeypatch.setattr(ga, "quant_engine", _FakeQuant(dict(ACTIONABLE)))
    monkeypatch.setattr(ai_providers, "is_configured", lambda provider=None: True)
    monkeypatch.setattr(ai_providers, "get_active_provider", lambda: "openai")
    monkeypatch.setattr(ai_providers, "get_model", lambda p: "gpt-4.1")
    monkeypatch.setattr(ai_providers, "generate_json", lambda *a, **k: {
        "verbal_pitch": "Buy at 150 with stop 140. Say Approve.",   # wrong levels
        "technical_rationale": "LLM rationale",
        "entry_price": 1, "stop_loss": 999,                         # ignored extras
    })
    out = GeminiMarketAnalyzer().analyze_market_setup("BANK NIFTY", {"ltp": 52000}, None)
    assert out["entry_price"] == 200.0 and out["stop_loss"] == 180.0
    assert out["technical_rationale"] == "LLM rationale"
    assert out["verbal_pitch"] == ACTIONABLE["verbal_pitch"]       # mismatched pitch discarded
    assert out["ai_model"] == "openai/gpt-4.1"


def test_llm_pitch_with_correct_levels_is_used(monkeypatch):
    import gemini_analyzer as ga
    monkeypatch.setattr(ga, "quant_engine", _FakeQuant(dict(ACTIONABLE)))
    monkeypatch.setattr(ai_providers, "is_configured", lambda provider=None: True)
    monkeypatch.setattr(ai_providers, "generate_json", lambda *a, **k: {
        "verbal_pitch": "Buy the call at ₹200.00, stop-loss ₹180. Say Approve.", "technical_rationale": "ok"})
    out = GeminiMarketAnalyzer().analyze_market_setup("BANK NIFTY", {"ltp": 52000}, None)
    assert out["verbal_pitch"].startswith("Buy the call")


def test_llm_failure_falls_back_to_rule_text(monkeypatch):
    import gemini_analyzer as ga
    monkeypatch.setattr(ga, "quant_engine", _FakeQuant(dict(ACTIONABLE)))
    monkeypatch.setattr(ai_providers, "is_configured", lambda provider=None: True)

    def boom(*a, **k):
        raise ai_providers.AIProviderError("down")

    monkeypatch.setattr(ai_providers, "generate_json", boom)
    out = GeminiMarketAnalyzer().analyze_market_setup("BANK NIFTY", {"ltp": 52000}, None)
    assert out["actionable"] is True and out["verbal_pitch"] == ACTIONABLE["verbal_pitch"]


def test_invalid_quant_levels_become_no_trade(monkeypatch):
    import gemini_analyzer as ga
    bad = dict(ACTIONABLE, stop_loss=210.0)
    monkeypatch.setattr(ga, "quant_engine", _FakeQuant(bad))
    out = GeminiMarketAnalyzer().analyze_market_setup("BANK NIFTY", {"ltp": 52000}, None)
    assert out["actionable"] is False


# --------------------------------------------------------------------------- AI providers

def test_provider_catalog_has_three_providers():
    assert set(ai_providers.PROVIDERS) == {"gemini", "openai", "anthropic"}
    for meta in ai_providers.PROVIDERS.values():
        assert meta["models"] and meta["default_model"]


class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._p, self.text = status, payload, str(payload)

    def json(self):
        return self._p


def test_openai_call_shape(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, body=json)
        return _Resp(200, {"choices": [{"message": {"content": '```json\n{"ok": true}\n```'}}]})

    monkeypatch.setattr(ai_providers.httpx, "post", fake_post)
    out = ai_providers.generate_json("hi", provider="openai", model="gpt-4.1", api_key="sk-test")
    assert out == {"ok": True}
    assert seen["url"].endswith("/chat/completions")
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    assert seen["body"]["model"] == "gpt-4.1"


def test_anthropic_call_shape(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, body=json)
        return _Resp(200, {"content": [{"type": "text", "text": '{"ok": true}'}]})

    monkeypatch.setattr(ai_providers.httpx, "post", fake_post)
    out = ai_providers.generate_json("hi", provider="anthropic", model="claude-sonnet-5-5", api_key="sk-ant-test")
    assert out == {"ok": True}
    assert seen["headers"]["x-api-key"] == "sk-ant-test"
    assert seen["body"]["model"] == "claude-sonnet-5-5"


def test_missing_key_and_http_error(monkeypatch):
    monkeypatch.setattr(ai_providers, "get_api_key", lambda p: "")
    with pytest.raises(ai_providers.AIProviderError, match="No API key"):
        ai_providers.generate_json("hi", provider="openai")
    monkeypatch.setattr(ai_providers.httpx, "post", lambda *a, **k: _Resp(401, {"error": "bad key"}))
    with pytest.raises(ai_providers.AIProviderError, match="401"):
        ai_providers.generate_json("hi", provider="openai", api_key="x")


# --------------------------------------------------------------------------- live execution

class FakeKite:
    """Minimal in-memory Kite: tracks orders; fills market orders instantly."""
    TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_SELL = "BUY", "SELL"
    EXCHANGE_NFO, EXCHANGE_NSE = "NFO", "NSE"
    VARIETY_REGULAR = "regular"
    PRODUCT_MIS = "MIS"
    ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET, ORDER_TYPE_SL, ORDER_TYPE_SLM = "LIMIT", "MARKET", "SL", "SL-M"
    VALIDITY_DAY = "DAY"

    def __init__(self, entry_fills=True, fail_sl=False):
        self.orders = {}
        self.placed = []
        self.entry_fills = entry_fills
        self.fail_sl = fail_sl
        self.n = 0

    def instruments(self, exch):
        return [{"name": "BANKNIFTY", "instrument_type": "CE", "strike": 52000.0,
                 "expiry": datetime.date.today() + datetime.timedelta(days=3),
                 "tradingsymbol": "BANKNIFTY25OCT52000CE", "lot_size": 30}]

    def place_order(self, **p):
        if p["order_type"] == "SL" and self.fail_sl:
            raise Exception("SL rejected by RMS")
        self.n += 1
        oid = f"OID{self.n}"
        self.placed.append(dict(p, order_id=oid))
        if p["order_type"] == "LIMIT":
            status = "COMPLETE" if self.entry_fills else "OPEN"
            self.orders[oid] = {"order_id": oid, "status": status,
                                "filled_quantity": p["quantity"] if self.entry_fills else 0,
                                "average_price": p["price"] if self.entry_fills else 0.0}
        elif p["order_type"] == "MARKET":
            self.orders[oid] = {"order_id": oid, "status": "COMPLETE", "filled_quantity": p["quantity"], "average_price": 150.0}
        else:
            self.orders[oid] = {"order_id": oid, "status": "TRIGGER PENDING", "filled_quantity": 0, "average_price": 0.0}
        return oid

    def order_history(self, oid):
        return [dict(self.orders[oid])]

    def cancel_order(self, variety, order_id):
        if self.orders[order_id]["status"] not in ("COMPLETE", "CANCELLED"):
            self.orders[order_id]["status"] = "CANCELLED"

    def modify_order(self, variety, order_id, **kw):
        self.orders[order_id].update(kw)

    def orders_list(self):
        return list(self.orders.values())


def _live_engine(fake, monkeypatch):
    import database
    monkeypatch.setattr(KiteExecutionEngine, "verify_outgoing_kite_request", lambda self: True)
    monkeypatch.setattr(KiteExecutionEngine, "ENTRY_FILL_TIMEOUT", 0.2)
    monkeypatch.setattr(KiteExecutionEngine, "EXIT_FILL_TIMEOUT", 0.2)
    engine = KiteExecutionEngine()
    engine.kite_client = fake
    engine.access_token = "tok"
    return engine


PROPOSAL = {
    "proposal_id": "pp1", "symbol": "BANK NIFTY", "instrument": "BANKNIFTY 52000 CE", "signal_type": "BUY_CALL",
    "entry_price": 200.0, "stop_loss": 180.0, "target_1": 240.0, "target_2": 260.0,
}


def test_live_entry_resolves_contract_quantity_and_places_broker_stop(monkeypatch):
    fake = FakeKite()
    engine = _live_engine(fake, monkeypatch)
    res = engine.execute_order(dict(PROPOSAL, proposal_id="pp-live-1"), lot_size=1)

    entry = fake.placed[0]
    assert entry["tradingsymbol"] == "BANKNIFTY25OCT52000CE"   # real exchange symbol, not the display label
    assert entry["quantity"] == 30                              # 1 lot x contract lot size
    stop = fake.placed[1]
    assert stop["order_type"] == "SL" and stop["transaction_type"] == "SELL"
    assert stop["trigger_price"] == 180.0 and stop["price"] < stop["trigger_price"]
    assert res["position"]["sl_order_id"] == stop["order_id"]
    assert res["position"]["quantity"] == 30


def test_unfilled_entry_is_cancelled_and_opens_no_position(monkeypatch):
    fake = FakeKite(entry_fills=False)
    engine = _live_engine(fake, monkeypatch)
    res = engine.execute_order(dict(PROPOSAL, proposal_id="pp-live-2"), lot_size=1)
    assert res["rejected"] is True and "position" not in res
    assert fake.orders["OID1"]["status"] == "CANCELLED"
    assert len(fake.placed) == 1  # no protective stop for a non-existent position


def test_failed_protective_stop_flattens_position(monkeypatch):
    fake = FakeKite(fail_sl=True)
    engine = _live_engine(fake, monkeypatch)
    res = engine.execute_order(dict(PROPOSAL, proposal_id="pp-live-3"), lot_size=1)
    assert res["rejected"] is True and "flattened" in res["message"]
    assert [p["order_type"] for p in fake.placed] == ["LIMIT", "MARKET"]
    assert fake.placed[1]["transaction_type"] == "SELL"


def test_close_cancels_stop_then_sells(monkeypatch):
    fake = FakeKite()
    engine = _live_engine(fake, monkeypatch)
    pos = engine.execute_order(dict(PROPOSAL, proposal_id="pp-live-4"), lot_size=1)["position"]
    price, ref = engine.close_live(pos)
    assert fake.orders[pos["order_id"] and "OID2"]["status"] == "CANCELLED"  # protective stop cancelled
    assert fake.placed[-1]["order_type"] == "MARKET" and fake.placed[-1]["transaction_type"] == "SELL"
    assert price == 150.0


def test_close_uses_filled_stop_without_sending_another_order(monkeypatch):
    fake = FakeKite()
    engine = _live_engine(fake, monkeypatch)
    pos = engine.execute_order(dict(PROPOSAL, proposal_id="pp-live-5"), lot_size=1)["position"]
    fake.orders[pos["sl_order_id"]].update(status="COMPLETE", average_price=179.5, filled_quantity=30)
    before = len(fake.placed)
    price, ref = engine.close_live(pos)
    assert price == 179.5 and ref == pos["sl_order_id"]
    assert len(fake.placed) == before  # no reverse position created


def test_unconfirmed_exit_is_not_duplicated(monkeypatch):
    fake = FakeKite()
    engine = _live_engine(fake, monkeypatch)
    pos = engine.execute_order(dict(PROPOSAL, proposal_id="pp-live-6"), lot_size=1)["position"]
    orig = fake.place_order

    def slow_market(**p):
        oid = orig(**p)
        if p["order_type"] == "MARKET":
            fake.orders[oid]["status"] = "OPEN"
        return oid

    fake.place_order = slow_market
    with pytest.raises(RuntimeError):
        engine.close_live(pos)
    market_orders = [p for p in fake.placed if p["order_type"] == "MARKET"]
    with pytest.raises(RuntimeError):
        engine.exit_position(pos)  # retry must not place a second market order
    assert len([p for p in fake.placed if p["order_type"] == "MARKET"]) == len(market_orders) == 1


def test_unified_close_does_not_mark_closed_when_exit_fails(monkeypatch):
    import database
    engine = UnifiedTradingEngine()
    pos = {
        "position_id": "POS-LIVE-X1", "symbol": "BANK NIFTY", "instrument": "BANKNIFTY 52000 CE",
        "signal_type": "BUY_CALL", "quantity": 30, "buy_price": 200.0, "current_ltp": 190.0,
        "stop_loss": 180.0, "target_1": 240.0, "target_2": 260.0, "status": "OPEN", "mode": "LIVE",
        "opened_at": "10:00:00", "broker_symbol": "BANKNIFTY25OCT52000CE", "exchange": "NFO",
    }
    database.save_position(pos)
    engine.positions[pos["position_id"]] = pos

    def fail(_pos):
        raise RuntimeError("broker down")

    monkeypatch.setattr(engine.kite_engine, "close_live", fail)
    with pytest.raises(RuntimeError, match="not confirmed"):
        engine.close_position(pos["position_id"], "STOP_LOSS_HIT")
    assert engine.positions[pos["position_id"]]["status"] == "OPEN"  # still tracked, retried next tick


def test_live_mode_never_falls_back_to_paper(monkeypatch):
    engine = UnifiedTradingEngine()
    engine.mode = "LIVE"
    engine.kite_engine.kite_client = None
    engine.access_token = ""
    sig = {
        "symbol": "NIFTY 50", "instrument_to_trade": "NIFTY 24850 CE", "signal_type": "BUY_CALL",
        "direction": "BULLISH", "entry_price": 100.0, "stop_loss": 90.0, "target_1": 120.0,
        "target_2": 130.0, "risk_reward": "1:2.0", "confidence": 80, "verbal_pitch": "x", "technical_rationale": "y",
    }
    proposal = engine.create_trade_proposal(sig)
    monkeypatch.setattr(engine, "_check_entry_drift", lambda p: None)
    with pytest.raises(ValueError, match="not connected"):
        engine.approve_trade(proposal["proposal_id"])
    assert len(engine.positions) == 0


# --------------------------------------------------------------------------- AI settings API

def test_ai_config_api_roundtrip():
    from fastapi.testclient import TestClient
    import database
    from security import create_session_token, invalidate_session_token
    from main import app

    client = TestClient(app)
    if not database.is_master_password_set():
        database.setup_master_password("TestMasterKey123!")
    token = create_session_token()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        cfg = client.get("/api/ai/config", headers=headers).json()
        assert {p["id"] for p in cfg["providers"]} == {"gemini", "openai", "anthropic"}

        res = client.post("/api/ai/config", headers=headers, json={
            "provider": "anthropic", "target_provider": "anthropic",
            "model": "claude-opus-5-5", "api_key": "sk-ant-secret-value-123"})
        assert res.status_code == 200
        body = res.json()
        assert body["active_provider"] == "anthropic"
        anth = next(p for p in body["providers"] if p["id"] == "anthropic")
        assert anth["model"] == "claude-opus-5-5" and anth["has_key"] is True
        assert "secret-value" not in str(body)          # raw key never returned

        bad = client.post("/api/ai/config", headers=headers, json={"provider": "nope"})
        assert bad.status_code == 400
    finally:
        client.post("/api/ai/config", headers=headers, json={"provider": "gemini"})
        invalidate_session_token(token)


# --------------------------------------------------------------------------- discipline limits

def _seed_closed(pnls_newest_first, minutes_ago=5, mode="PAPER"):
    import database
    conn = database.get_db_connection()
    try:
        conn.execute("DELETE FROM positions")
        conn.commit()
    finally:
        conn.close()
    base = datetime.datetime.now() - datetime.timedelta(minutes=minutes_ago)
    for n, pnl in enumerate(reversed(pnls_newest_first)):
        closed = (base - datetime.timedelta(minutes=len(pnls_newest_first) - n)).strftime("%Y-%m-%d %H:%M:%S")
        database.save_position({
            "position_id": f"POS-SEED-{n}-{minutes_ago}", "symbol": "RELIANCE", "instrument": "RELIANCE MIS",
            "signal_type": "BUY_EQUITY", "quantity": 1, "buy_price": 100.0, "current_ltp": 100.0,
            "stop_loss": 90.0, "target_1": 120.0, "target_2": 130.0, "status": "CLOSED", "mode": mode,
            "realized_pnl": pnl, "exit_price": 100.0, "close_reason": "X", "opened_at": "10:00:00", "closed_at": closed,
        })
    # Newest closed time should be `base`; the oldest earlier.


def _paper_engine():
    engine = UnifiedTradingEngine()
    engine.mode = "PAPER"
    engine.positions.clear()
    return engine


def test_trade_cap_blocks_new_entries(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "MAX_TRADES_PER_DAY", 3)
    _seed_closed([5.0, 5.0, 5.0])
    with pytest.raises(ValueError, match="Daily trade limit"):
        _paper_engine()._check_trading_limits()
    monkeypatch.setattr(settings, "MAX_TRADES_PER_DAY", 4)
    _paper_engine()._check_trading_limits()   # one slot left: allowed


def test_loss_streak_pauses_then_resumes(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "MAX_TRADES_PER_DAY", 100)
    monkeypatch.setattr(settings, "MAX_CONSECUTIVE_LOSSES", 3)
    monkeypatch.setattr(settings, "LOSS_STREAK_PAUSE_MINUTES", 60)

    _seed_closed([-10.0, -10.0, -10.0], minutes_ago=5)           # three straight losses just now
    with pytest.raises(ValueError, match="paused"):
        _paper_engine()._check_trading_limits()

    _seed_closed([-10.0, -10.0, -10.0], minutes_ago=120)         # pause window has passed
    _paper_engine()._check_trading_limits()

    _seed_closed([-10.0, 25.0, -10.0, -10.0], minutes_ago=5)     # a win breaks the streak
    _paper_engine()._check_trading_limits()


def test_limits_are_per_mode(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "MAX_TRADES_PER_DAY", 2)
    _seed_closed([1.0, 1.0, 1.0], mode="LIVE")
    _paper_engine()._check_trading_limits()   # live-mode history must not block paper practice


# --------------------------------------------------------------------------- startup reconcile

def test_reconcile_books_positions_the_broker_already_closed(monkeypatch):
    import database
    fake = FakeKite()
    fake.positions = lambda: {"net": [{"tradingsymbol": "BANKNIFTY25OCT52000CE", "quantity": 0}]}
    engine = UnifiedTradingEngine()
    engine.kite_engine.kite_client = fake
    monkeypatch.setattr(engine, "is_authenticated", lambda: True)
    monkeypatch.setattr(KiteExecutionEngine, "verify_outgoing_kite_request", lambda self: True)
    fake.orders["SL1"] = {"order_id": "SL1", "status": "COMPLETE", "average_price": 181.0, "filled_quantity": 30}
    pos = {
        "position_id": "POS-LIVE-R1", "symbol": "BANK NIFTY", "instrument": "BANKNIFTY 52000 CE",
        "signal_type": "BUY_CALL", "quantity": 30, "buy_price": 200.0, "current_ltp": 195.0, "stop_loss": 180.0,
        "target_1": 240.0, "target_2": 260.0, "status": "OPEN", "mode": "LIVE", "opened_at": "10:00:00",
        "broker_symbol": "BANKNIFTY25OCT52000CE", "exchange": "NFO", "sl_order_id": "SL1",
    }
    database.save_position(pos)
    engine.positions.clear()
    engine.positions[pos["position_id"]] = pos

    report = engine.reconcile_live_positions()
    assert report["closed_locally"] == ["POS-LIVE-R1"]
    assert pos["status"] == "CLOSED" and pos["exit_price"] == 181.0     # the stop's real fill price
    assert "POS-LIVE-R1" not in engine.positions


def test_reconcile_reports_untracked_broker_positions(monkeypatch):
    fake = FakeKite()
    fake.positions = lambda: {"net": [{"tradingsymbol": "SOMETHINGELSE", "quantity": -50}]}
    engine = UnifiedTradingEngine()
    engine.positions.clear()
    engine.kite_engine.kite_client = fake
    monkeypatch.setattr(engine, "is_authenticated", lambda: True)
    monkeypatch.setattr(KiteExecutionEngine, "verify_outgoing_kite_request", lambda self: True)
    assert engine.reconcile_live_positions()["untracked_at_broker"] == ["SOMETHINGELSE"]
