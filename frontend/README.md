# TradeSentinel: Frontend

React 19 + TypeScript (strict) + Vite trading terminal. See the [root README](../README.md) for the whole system.

## Structure

```
src/
├── features/
│   ├── auth/        AuthGatekeeper: master password setup and unlock
│   ├── market/      Watchlist, TradingChart (Lightweight Charts v5 with EMA/VWAP overlays)
│   ├── trading/     TradeProposalCard (60 s approval), PositionsTable, HistoryTracker
│   ├── settings/    SettingsModal (Kite, notifications), AIProviderSettings (provider, model, key)
│   └── voice/       VoiceRadar (Web Speech commands)
├── hooks/           All stateful logic: useAuthSession, useLiveTradingData (REST + websocket),
│                    useTradeActions (scan/approve/reject/close + shortcuts), useCandles, useTokenHeartbeat
├── components/layout/  Header, KiteSetupBanner
├── services/        Typed API client, speech, sound, desktop notifications
├── constants/       Shared constants
└── types/           Domain interfaces (Quote, Candle, TradeProposal, Position, ...)
```

`App.tsx` only composes the hooks and lays out the screen.

## Scripts

| Command | What it does |
| :-- | :-- |
| `npm run dev` | Vite dev server on :5173 (talks to the API on port 8000 of the same host) |
| `npm test` | Vitest + Testing Library (hooks, components, API helpers) |
| `npm run typecheck` | `tsc -b` with `strict` on |
| `npm run lint` | oxlint |
| `npm run build` | Type-check and production build |

Set `VITE_API_BASE_URL` to point at another backend; an empty value means same-origin (used by the Docker/nginx setup).

## Keyboard shortcuts

| Key | Action |
| :-- | :-- |
| `A` / `Enter` | Approve pending proposal |
| `R` / `Esc` | Reject pending proposal |
| `S` | Scan selected symbol |

## Scripts

```bash
npm ci            # install
npm run dev       # dev server on :5173
npm run build     # type-check (tsc -b) and production build
npm run lint      # oxlint
```

The API base URL is derived from the page's hostname on port 8000 (`src/services/api.ts`).
