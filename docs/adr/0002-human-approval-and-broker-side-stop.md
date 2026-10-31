# ADR 0002: Human approval for every entry, broker-side stop-loss for every live position

- Status: accepted

## Context
Two failure modes matter most for an automated trading tool: it opens a position nobody intended, and it loses
connection (or crashes) while a position is open.

## Decision
- No order is sent until the user approves a proposal, within a 60-second server-enforced window.
- Every live entry is followed immediately by a stop-loss order resting at the broker. If that stop cannot be placed,
  the position is flattened at once rather than left unprotected.
- A position is only marked closed after the broker confirms the exit order. The engine never sends a second exit while
  one is unresolved (it polls to a terminal state first), and a software exit cancels and confirms the resting stop
  before selling, to avoid a double sell.
- LIVE mode never silently falls back to paper.

## Consequences
- A crash or lost connection leaves the position protected by the broker's stop.
- Targets are managed in software only: Zerodha has no OCO for MIS orders, so a resting target next to the stop could
  fill both. This is documented under known limitations.
- Reconciliation (`trading/reconciliation.py`) re-syncs local state with the broker after restarts or manual exits.
