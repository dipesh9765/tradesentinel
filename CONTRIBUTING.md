# Contributing

## Setup
```bash
make install          # backend (pip) + frontend (npm ci)
make backend          # API on :8000
make frontend         # UI on :5173
```

## Before opening a pull request
```bash
make check            # ruff, oxlint, mypy, tsc, pytest (coverage gate), vitest
```
CI runs the same commands plus a Docker build and smoke test. Optional: `pre-commit install` to format on commit.

## Conventions
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`).
- Backend code lives under `backend/app/` by layer (see [ARCHITECTURE.md](ARCHITECTURE.md) and [docs/adr](docs/adr)).
  Keep decisions in `strategy/` pure and deterministic; keep broker I/O in `trading/kite_broker.py`.
- Anything that can place or modify an order needs a test, and live-order paths are tested against the fake broker client
  in `backend/tests/test_reliability.py`.
- Frontend logic belongs in `src/hooks/`; components stay presentational. No `any` in new code.
- Do not weaken a risk control (limits, approval window, broker-side stop) without an ADR explaining why.
