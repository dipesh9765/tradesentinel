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
├── components/layout/  Header: mode switch, connection and P&L status
├── services/        Typed API client, speech, sound, desktop notifications
├── constants/       Shared constants
└── types/           Domain interfaces (Quote, Candle, TradeProposal, Position, ...)
```

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
