# Threat model

Scope: a single-user, self-hosted trading assistant that holds broker and AI-provider credentials and can place
real orders. Out of scope: multi-tenant hosting.

## Assets
1. Broker API key, secret and daily access token (can place and cancel real orders).
2. AI-provider API keys (cost and abuse exposure).
3. The master password and the session token derived from it.
4. Integrity of orders: nothing should be placed that the user did not approve.

## Trust boundaries
Browser <-> API (same host or reverse proxy) · API <-> SQLite file · API <-> Zerodha Kite · API <-> LLM providers ·
API <-> notification webhooks.

## Threats and mitigations

| # | Threat | Mitigation | Residual risk |
| :-- | :-- | :-- | :-- |
| T1 | Stolen database file exposes credentials | Credentials encrypted with Fernet; key derived from the master password via PBKDF2 and a per-vault salt; password stored only as a salted hash | PBKDF2 is 100,000 iterations (below current OWASP guidance for SHA-256); a weak master password is brute-forceable offline. Roadmap: versioned hash format with a higher iteration count |
| T2 | Online guessing of the master password | Per-client login throttling (5 failures, 60 s lockout); constant-time comparison | Throttle is in memory and per client address |
| T3 | Stolen or leaked session token | Random 256-bit-class URL-safe tokens, fixed 24 h lifetime, in memory only, invalidated on logout; every non-public route requires auth | Token is held in browser `localStorage`; XSS would expose it. No CSP is set by the app itself (the bundled nginx adds basic security headers) |
| T4 | Unauthorised or accidental order | Server-enforced 60 s human approval for every entry; signal validation; 1-lot cap; daily loss, trade-count and loss-streak limits counted from the database | Approval depends on the user reading the proposal |
| T5 | LLM hallucination or prompt injection changes a trade | The model never supplies price levels; prices quoted by the model that differ from the rules engine are discarded; model output is used only as text | Explanation text could still be misleading; it is labelled as an explanation, not a decision |
| T6 | Position left unprotected after a crash or disconnect | Broker-side stop-loss placed with every live entry; flatten immediately if the stop cannot be placed; reconciliation on start | Targets are software-managed (no OCO for MIS orders) |
| T7 | Double exit (two sell orders) | Single re-entrant lock around approvals and closes; confirmed cancel of the resting stop before a software exit; no new exit while one is unresolved | Manual action in the broker's own app can still race the engine; reconciliation detects it |
| T8 | Secrets leaked via logs | Request/response audit middleware masks sensitive fields before logging | New fields need to be added to the mask list |
| T9 | Cross-origin abuse of the API | CORS allow-list (localhost, private ranges, optional `CORS_EXTRA_ORIGINS`); all state-changing routes require a Bearer token, not cookies | Private-range origins are intentionally allowed for LAN use |
| T10 | Vulnerable dependencies | Pinned versions, `npm audit` clean at release time, CI | No automated dependency update bot yet |
| T11 | Container compromise | Non-root user, ports bound to 127.0.0.1 in compose, healthchecks | Volume holds the encrypted database; protect the host |

## Assumptions
- The host and browser are not already compromised.
- The user keeps the master password private and uses a strong one.
- Live trading is first run supervised, with the smallest size.

## Reporting
See [SECURITY.md](../SECURITY.md).
