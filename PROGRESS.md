# PROGRESS: tradesentinel overhaul

## Baseline (audited 2026-10-26)
- Backend: 81 pytest tests pass (38 s). Frontend: `tsc -b && vite build` OK, `oxlint` gives warnings only.
- CI exists (pytest, build, lint) but has no type check, no backend lint/format, no coverage, no Docker build.

## Findings (what an interviewer would notice)
1. **Layout is half-migrated.** Root-level modules (`kite_executor.py` 1510 lines, `database.py`, `market_data.py`, ...) sit beside an `app/` package; `main.py`, `config.py`, `genConsts.py`, `prompts.py` at the root are shims over `app/`. Should be one proper package (`app/` with domain, services, adapters, api).
2. **God module**: `kite_executor.py` holds the broker adapter and `UnifiedTradingEngine` (orchestration, risk, reconciliation). Split into broker adapter / risk manager / order lifecycle / reconciliation.
3. **Frontend**: `App.tsx` is 596 lines with `react(immutability)` and `exhaustive-deps` lint warnings; no frontend tests.
4. **No Docker / compose, no Makefile, no pre-commit**, no coverage badge, no ruff/mypy config.
5. **Windows-only starters** (`.bat`); add cross-platform scripts.
6. README is already strong; add a latency/perf section, an ADR folder, and a threat model.

## Plan
- [x] A. Ruff + mypy (strict where feasible) + coverage in CI; fix findings
- [x] B. Restructure backend into one package; delete shims; keep tests green
- [x] C. Split `kite_executor.py`; add targeted tests for each part
- [x] D. Frontend: extract hooks from `App.tsx`, fix lint, add Vitest + Testing Library tests
- [ ] E. Dockerfile(s) + docker-compose, Makefile, pre-commit
- [ ] F. docs/adr/*, THREAT_MODEL.md, SECURITY.md, CONTRIBUTING.md, tag v1.0.0
- [ ] G. Resume bullets into `../RESUME_BULLETS.md`

## Decisions log
- Work on branch `overhaul/v1`; nothing pushed without approval.

## Log
- A: ruff/mypy/coverage added; fixed scan default-symbol bug (omitted symbol was passed as None), unchained exceptions, dangling asyncio task, TRADE_EXPLANATION prompt binding.
- B: single `app/` package (core, db, strategy, ai, market, trading, services); shims removed; entrypoint is `app.main:app`.
- C: `kite_executor.py` (1510 lines) split into engine + risk/session/reconciliation/monitor mixins over a typed `EngineState`, and `kite_broker`. Singleton renamed `trading_engine`. 92 tests, mypy clean.
- D: App.tsx 596 -> ~280 lines; logic moved to hooks (useAuthSession, useLiveTradingData, useTradeActions, useCandles, useTokenHeartbeat), KiteSetupBanner extracted, `any` removed from the new code, strict tsc on, lint clean, Vitest + Testing Library (44 tests), npm audit fixed (vite advisory).
