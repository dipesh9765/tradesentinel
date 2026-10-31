# Changelog

## 1.0.0

### Added
- `/healthz` and `/readyz` probes; `CORS_EXTRA_ORIGINS` and `VITE_API_BASE_URL` settings.
- Dockerfiles for the API and UI (non-root, healthchecks), nginx proxy, `docker-compose.yml`, Makefile, pre-commit.
- Ruff, mypy and a 70% coverage gate in CI; a Docker build and smoke-test job.
- Vitest and Testing Library suite (44 tests) and component tests for risk, monitoring and composition (95 backend tests in total).
- Architecture decision records, threat model, security policy and contributing guide.

### Changed
- Backend consolidated into one layered `app/` package; entrypoint is `app.main:app`.
- `kite_executor.py` split into `engine`, `risk`, `session`, `reconciliation`, `monitor` and `kite_broker`.
- `App.tsx` logic moved into hooks (`useAuthSession`, `useLiveTradingData`, `useTradeActions`, `useCandles`, `useTokenHeartbeat`).
- TypeScript `strict` enabled; frontend dependency advisories resolved.

### Fixed
- Scanning without a symbol passed `None` to the analyzer instead of using the first watchlist symbol.
- Re-raised exceptions now keep their cause; fire-and-forget notification tasks are no longer garbage collected.
- The trade-explanation prompt was attached to `GenPrompts` as an untyped attribute; it is now declared on the class.
- Risk-limit tests were time-of-day dependent and failed within minutes of midnight; they now run on a frozen clock.
