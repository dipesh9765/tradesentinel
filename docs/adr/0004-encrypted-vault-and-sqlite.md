# ADR 0004: Encrypted SQLite vault instead of a secrets service

- Status: accepted

## Context
The app stores broker and AI-provider credentials. It is a single-user tool that should run on a laptop with no
infrastructure, so a managed secrets service or a server database is out of proportion.

## Decision
Credentials are encrypted with Fernet (AES-128-CBC with HMAC-SHA256) using a key derived from the master password with
PBKDF2-HMAC-SHA256 and a per-vault random salt. The password itself is stored only as a salted PBKDF2 hash and compared
in constant time. Data lives in SQLite with WAL journaling and a 30-second busy timeout. Sessions are random URL-safe
tokens held in memory with a fixed 24-hour lifetime; login failures are throttled.

## Consequences
- Zero setup: one file, one master password.
- Sessions are lost on restart (acceptable for a single-user tool) and the design is not multi-tenant.
- PBKDF2 uses 100,000 iterations, below current OWASP guidance for SHA-256. Raising it requires a versioned hash
  format so existing vaults keep working; it is tracked in the roadmap and the threat model.
