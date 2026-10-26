# ADR 0005: One layered `app` package; the trading engine is composed of focused components

- Status: accepted

## Context
The backend had grown as root-level modules next to an `app/` package, with shims re-exporting between them, and a
single 1,500-line module that held the broker adapter and the orchestration, risk, reconciliation and monitoring logic.

## Decision
- One package, `app/`, organised by layer: `core` (config, constants, security, interfaces), `db`, `strategy`, `ai`,
  `market`, `trading`, `services`, plus the thin `api` layer. The only entrypoint is `app.main:app`.
- `trading/kite_broker.py` is the live broker adapter. `UnifiedTradingEngine` keeps the proposal and close lifecycle and
  is composed of four components: `RiskMixin`, `BrokerSessionMixin`, `ReconciliationMixin` and `PositionMonitorMixin`.
  They share portfolio state, which is declared once in `trading/state.py` so mypy can check every cross-component call.
- Ruff and mypy run in CI; the coverage gate is 70% for the backend.

## Consequences
- Each concern has a small file and its own tests (`tests/test_trading_components.py`).
- Mixins share mutable state by design (a single lock serialises approvals and closes). If a second broker is added, the
  next step is to extract these into collaborator objects behind `BaseOrderExecutor` rather than grow the mixins.
