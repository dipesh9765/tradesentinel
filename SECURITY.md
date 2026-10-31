# Security policy

## Reporting a vulnerability
Please do not open a public issue for a security problem. Use GitHub's private vulnerability reporting
("Security" tab -> "Report a vulnerability") on this repository, and include steps to reproduce.
You can expect an acknowledgement within a few days.

## Supported versions
Only the latest release on `main` receives fixes.

## Handling credentials
- Never commit `.env` files, broker keys or tokens. `.gitignore` excludes them; `.env.example` is the only tracked template.
- Credentials entered in the UI are stored encrypted in the local vault (see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)).
- If a credential is ever committed, rotate it immediately; removing it from history is not enough.

## Design notes
The threat model, including known limitations (for example the PBKDF2 iteration count), is in
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).
