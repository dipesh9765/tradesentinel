"""
Cryptographic Security & Session Vault Architecture - TradeSentinel

This module implements enterprise security protocols protecting trading credentials
and authorization barriers:
1. PBKDF2-HMAC-SHA256 password hashing with 100,000 iterations and 16-byte random salts.
2. Constant-time timing-attack mitigation using `secrets.compare_digest`.
3. Master Key Derivation Function (KDF) producing 32-byte URL-safe base64 keys.
4. AES-128-CBC encryption with PKCS7 padding and HMAC-SHA256 authentication (via Fernet).
5. In-memory session tokens with a fixed 24-hour lifetime and cryptographic entropy (secrets.token_urlsafe).
6. Login brute-force throttling: repeated failures from one client lock further attempts briefly.
"""

import base64
import hashlib
import os
import secrets
import time

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# In-memory active session tokens: token -> {"created_at": float, "expires_at": float}
ACTIVE_SESSIONS: dict[str, dict[str, float]] = {}
SESSION_DURATION_SECONDS: int = 86400  # fixed 24-hour lifetime


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """
    Hashes a plain master password using PBKDF2-HMAC-SHA256 with 100,000 rounds.

    Args:
        password: Plain text password string.
        salt: Optional 16-byte cryptographic salt. If None, os.urandom(16) is generated.

    Returns:
        Tuple of (hex_encoded_hash, hex_encoded_salt).
    """
    if salt is None:
        salt = os.urandom(16)

    pwd_bytes = password.encode("utf-8")
    key = hashlib.pbkdf2_hmac("sha256", pwd_bytes, salt, 100000)
    return key.hex(), salt.hex()


def verify_password(password: str, stored_hash: str, stored_salt_hex: str) -> bool:
    """
    Verifies a plain password against the stored hex hash and salt using constant-time comparison.

    Args:
        password: Plain text password attempt.
        stored_hash: Hexadecimal hash stored in SQLite auth_config.
        stored_salt_hex: Hexadecimal salt stored in SQLite auth_config.

    Returns:
        bool: True if password matches, False otherwise.
    """
    salt = bytes.fromhex(stored_salt_hex)
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, stored_hash)


def derive_fernet_key(master_secret: str, salt: bytes) -> bytes:
    """
    Derives a 32-byte URL-safe base64 key suitable for Fernet symmetric encryption.

    Args:
        master_secret: Plain text master password string.
        salt: Cryptographic salt bytes.

    Returns:
        bytes: 32-byte URL-safe base64-encoded encryption key.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = kdf.derive(master_secret.encode("utf-8"))
    return base64.urlsafe_b64encode(key)


def encrypt_value(plain_text: str, encryption_key: bytes) -> str:
    """
    Encrypts a plain text string into an authenticated Fernet ciphertext token.

    Args:
        plain_text: Sensitive string to protect (e.g. Kite API secret or access token).
        encryption_key: 32-byte Fernet key derived from master password.

    Returns:
        str: Fernet ciphertext string.
    """
    if not plain_text:
        return ""
    f = Fernet(encryption_key)
    return f.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_value(cipher_text: str, encryption_key: bytes) -> str:
    """
    Decrypts an authenticated Fernet ciphertext token back to plain text.

    Args:
        cipher_text: Encrypted token string from secure_vault.
        encryption_key: 32-byte Fernet key derived from master password.

    Returns:
        str: Decrypted original string, or empty string on failure.
    """
    if not cipher_text:
        return ""
    try:
        f = Fernet(encryption_key)
        return f.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""


def create_session_token() -> str:
    """
    Generates a cryptographically strong URL-safe 32-byte session token with a 24-hour TTL.

    Returns:
        str: Generated session token string.
    """
    token = secrets.token_urlsafe(32)
    now = time.time()
    ACTIVE_SESSIONS[token] = {"created_at": now, "expires_at": now + SESSION_DURATION_SECONDS}
    return token


def validate_session_token(token: str | None) -> bool:
    """
    Validates whether an incoming HTTP Bearer token is registered and has not expired.

    Args:
        token: Bearer token string.

    Returns:
        bool: True if token is valid, False otherwise.
    """
    if not token:
        return False
    session = ACTIVE_SESSIONS.get(token)
    if not session:
        return False
    if time.time() > session["expires_at"]:
        del ACTIVE_SESSIONS[token]
        return False
    return True


def invalidate_session_token(token: str) -> None:
    """
    Revokes and deletes an active session token upon user logout.

    Args:
        token: Session token string to revoke.
    """
    ACTIVE_SESSIONS.pop(token, None)


def cleanup_expired_sessions() -> int:
    """
    Purges all stale and expired tokens from the active session table.

    Returns:
        int: Number of expired sessions purged.
    """
    now = time.time()
    expired = [tok for tok, s in ACTIVE_SESSIONS.items() if now > s["expires_at"]]
    for tok in expired:
        del ACTIVE_SESSIONS[tok]
    return len(expired)


def has_active_session() -> bool:
    """
    Checks if at least one authenticated active session currently exists.

    Returns:
        bool: True if valid session exists, False otherwise.
    """
    cleanup_expired_sessions()
    return len(ACTIVE_SESSIONS) > 0


# ---------------------------------------------------------------------------
# Login brute-force throttling (in memory, per client key such as an IP address)
# ---------------------------------------------------------------------------

MAX_LOGIN_FAILURES: int = 5
LOGIN_LOCKOUT_SECONDS: int = 60
LOGIN_FAILURE_WINDOW_SECONDS: int = 300
_LOGIN_FAILURES: dict[str, list] = {}


def login_lockout_remaining(client_key: str) -> int:
    """Seconds a client must still wait before another login attempt (0 when allowed)."""
    now = time.time()
    recent = [t for t in _LOGIN_FAILURES.get(client_key, []) if now - t < LOGIN_FAILURE_WINDOW_SECONDS]
    _LOGIN_FAILURES[client_key] = recent
    if len(recent) >= MAX_LOGIN_FAILURES:
        return max(0, int(recent[-1] + LOGIN_LOCKOUT_SECONDS - now) + 1)
    return 0


def register_login_failure(client_key: str) -> None:
    _LOGIN_FAILURES.setdefault(client_key, []).append(time.time())


def clear_login_failures(client_key: str) -> None:
    _LOGIN_FAILURES.pop(client_key, None)
