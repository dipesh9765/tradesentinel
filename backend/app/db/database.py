"""
Database & Encrypted Secure Vault Management Layer - TradeSentinel

This module implements the persistence layer for trade suggestions, positions, order audit logs,
and sensitive brokerage API credentials. It provides an ACID-compliant SQLite implementation
featuring:
1. Repository Pattern (`TradingRepository`) for structured Data Access Object (DAO) operations.
2. Master Password hashing using PBKDF2-HMAC-SHA256 with 100,000 iterations and random salts.
3. AES-128 (Fernet) cryptographic envelope for zero-plaintext credential storage on disk.
4. SQLite Write-Ahead Logging (WAL) and 30-second busy timeout for high-concurrency read/write.
5. Complete backward-compatible procedural facades for all existing consumers.
"""

import datetime
import os
import sqlite3
from typing import Any

from app.core.config import BASE_DIR
from app.core.genConsts import GenConsts
from app.core.server_logger import log_config_saved

# In-memory unlocked Fernet encryption key (never persisted to disk in plaintext)
_unlocked_encryption_key: bytes | None = None


def get_db_path() -> str:
    """Returns the absolute file path to the SQLite database."""
    return os.environ.get("TRADING_DB_PATH", str(BASE_DIR / GenConsts.DB_NAME))


def get_db_connection() -> sqlite3.Connection:
    """
    Creates and configures an SQLite connection with Row factory and 30s busy timeout.

    Returns:
        sqlite3.Connection: Active database connection.
    """
    conn = sqlite3.connect(get_db_path(), timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Initializes database tables, indices, and schema migrations with WAL journal mode.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 30000")

        # Trade Suggestions Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id TEXT UNIQUE NOT NULL,
            symbol TEXT NOT NULL,
            instrument TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            lot_size INTEGER DEFAULT 1,
            entry_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            target_1 REAL NOT NULL,
            target_2 REAL NOT NULL,
            risk_reward TEXT,
            confidence INTEGER,
            verbal_pitch TEXT,
            technical_rationale TEXT,
            status TEXT DEFAULT 'PENDING_APPROVAL',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        # Positions Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id TEXT UNIQUE NOT NULL,
            proposal_id TEXT,
            order_id TEXT,
            symbol TEXT NOT NULL,
            instrument TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            buy_price REAL NOT NULL,
            current_ltp REAL NOT NULL,
            stop_loss REAL NOT NULL,
            target_1 REAL NOT NULL,
            target_2 REAL NOT NULL,
            unrealized_pnl REAL DEFAULT 0.0,
            realized_pnl REAL DEFAULT 0.0,
            pnl_pct REAL DEFAULT 0.0,
            exit_price REAL,
            status TEXT DEFAULT 'OPEN',
            close_reason TEXT,
            mode TEXT DEFAULT 'PAPER',
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            FOREIGN KEY (proposal_id) REFERENCES trade_suggestions (proposal_id)
        )
        """)

        # Orders Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE NOT NULL,
            proposal_id TEXT,
            instrument TEXT NOT NULL,
            order_type TEXT NOT NULL,
            quantity INTEGER DEFAULT 1,
            price REAL NOT NULL,
            status TEXT NOT NULL,
            mode TEXT DEFAULT 'PAPER',
            pnl REAL,
            timestamp TEXT NOT NULL,
            status_message TEXT
        )
        """)

        # Schema migration check for status_message column in orders
        cursor.execute("PRAGMA table_info(orders)")
        columns = [row[1] for row in cursor.fetchall()]
        if "status_message" not in columns:
            cursor.execute("ALTER TABLE orders ADD COLUMN status_message TEXT")

        # Schema migration: broker linkage columns for live positions (protective stop / exit tracking)
        cursor.execute("PRAGMA table_info(positions)")
        pos_columns = [row[1] for row in cursor.fetchall()]
        for col in ("sl_order_id", "exit_order_id", "broker_symbol", "exchange"):
            if col not in pos_columns:
                cursor.execute(f"ALTER TABLE positions ADD COLUMN {col} TEXT")

        # Auth Config Table (Stores master password hash & salt)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS auth_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            master_key_salt TEXT NOT NULL,
            is_initialized INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """)

        # Encrypted Secure Vault Table (Stores encrypted API keys & secrets)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS secure_vault (
            key TEXT PRIMARY KEY NOT NULL,
            encrypted_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        conn.commit()
    finally:
        conn.close()


class TradingRepository:
    """
    Data Access Object (DAO) providing strongly-typed SQLite repository operations.
    """

    @staticmethod
    def save_suggestion(proposal: dict[str, Any]) -> None:
        """Persists or updates an AI/quantitative trade proposal."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """
            INSERT OR REPLACE INTO trade_suggestions (
                proposal_id, symbol, instrument, signal_type, direction,
                lot_size, entry_price, stop_loss, target_1, target_2,
                risk_reward, confidence, verbal_pitch, technical_rationale,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    proposal["proposal_id"],
                    proposal["symbol"],
                    proposal["instrument"],
                    proposal["signal_type"],
                    proposal["direction"],
                    proposal.get("lot_size", 1),
                    proposal["entry_price"],
                    proposal["stop_loss"],
                    proposal["target_1"],
                    proposal["target_2"],
                    proposal.get("risk_reward", "1:2.0"),
                    proposal.get("confidence", 85),
                    proposal.get("verbal_pitch", ""),
                    proposal.get("technical_rationale", ""),
                    proposal.get("status", "PENDING_APPROVAL"),
                    proposal.get("created_at", now),
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def update_suggestion_status(proposal_id: str, status: str) -> None:
        """Updates the status of a proposal (e.g. APPROVED, REJECTED)."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """
            UPDATE trade_suggestions SET status = ?, updated_at = ? WHERE proposal_id = ?
            """,
                (status, now, proposal_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def save_position(pos: dict[str, Any]) -> None:
        """Persists or updates an active position record."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
            INSERT OR REPLACE INTO positions (
                position_id, proposal_id, order_id, symbol, instrument,
                signal_type, quantity, buy_price, current_ltp, stop_loss,
                target_1, target_2, unrealized_pnl, realized_pnl, pnl_pct,
                exit_price, status, close_reason, mode, opened_at, closed_at,
                sl_order_id, exit_order_id, broker_symbol, exchange
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    pos["position_id"],
                    pos.get("proposal_id"),
                    pos.get("order_id"),
                    pos["symbol"],
                    pos["instrument"],
                    pos["signal_type"],
                    pos["quantity"],
                    pos["buy_price"],
                    pos["current_ltp"],
                    pos["stop_loss"],
                    pos["target_1"],
                    pos["target_2"],
                    pos.get("unrealized_pnl", 0.0),
                    pos.get("realized_pnl", 0.0),
                    pos.get("pnl_pct", 0.0),
                    pos.get("exit_price"),
                    pos.get("status", "OPEN"),
                    pos.get("close_reason"),
                    pos.get("mode", "PAPER"),
                    pos.get("opened_at"),
                    pos.get("closed_at"),
                    pos.get("sl_order_id"),
                    pos.get("exit_order_id"),
                    pos.get("broker_symbol"),
                    pos.get("exchange"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def update_position_in_db(pos: dict[str, Any]) -> None:
        """Updates live metrics, exit prices, and statuses for a position."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
            UPDATE positions SET
                current_ltp = ?, unrealized_pnl = ?, realized_pnl = ?,
                pnl_pct = ?, exit_price = ?, status = ?, close_reason = ?, closed_at = ?,
                stop_loss = ?, sl_order_id = ?, exit_order_id = ?
            WHERE position_id = ?
            """,
                (
                    pos["current_ltp"],
                    pos.get("unrealized_pnl", 0.0),
                    pos.get("realized_pnl", 0.0),
                    pos.get("pnl_pct", 0.0),
                    pos.get("exit_price"),
                    pos["status"],
                    pos.get("close_reason"),
                    pos.get("closed_at"),
                    pos["stop_loss"],
                    pos.get("sl_order_id"),
                    pos.get("exit_order_id"),
                    pos["position_id"],
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def update_position_pnl(
        position_id: str, current_ltp: float, unrealized_pnl: float, pnl_pct: float
    ) -> None:
        """Fast-path update for live quote tick recalculations."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
            UPDATE positions SET current_ltp = ?, unrealized_pnl = ?, pnl_pct = ? WHERE position_id = ?
            """,
                (current_ltp, unrealized_pnl, pnl_pct, position_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def update_position_status(
        position_id: str, status: str, exit_price: float, realized_pnl: float, close_reason: str
    ) -> None:
        """Marks a position as CLOSED with final realized accounting."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
            UPDATE positions SET
                status = ?, exit_price = ?, realized_pnl = ?,
                unrealized_pnl = 0.0, close_reason = ?, closed_at = ?
            WHERE position_id = ?
            """,
                (status, exit_price, realized_pnl, close_reason, now, position_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get_position_by_id(position_id: str) -> dict[str, Any] | None:
        """Fetches a position record by its unique position_id."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM positions WHERE position_id = ?", (position_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def get_open_positions_from_db() -> dict[str, dict[str, Any]]:
        """Returns all currently OPEN positions indexed by position_id."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM positions WHERE status = 'OPEN'")
            rows = cursor.fetchall()
            return {r["position_id"]: dict(r) for r in rows}
        finally:
            conn.close()

    @staticmethod
    def get_closed_positions_on(date_prefix: str, mode: str) -> list[dict[str, Any]]:
        """Positions closed on a given day (YYYY-MM-DD) in a trading mode, newest first."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT position_id, realized_pnl, closed_at FROM positions "
                "WHERE status = 'CLOSED' AND mode = ? AND closed_at LIKE ? "
                "ORDER BY closed_at DESC, id DESC",
                (mode, date_prefix + "%"),
            )
            return [dict(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    @staticmethod
    def save_order(order: dict[str, Any], proposal_id: str | None = None) -> None:
        """Inserts an order transmission or completion log into the immutable audit table."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
            INSERT OR REPLACE INTO orders (
                order_id, proposal_id, instrument, order_type, quantity, price, status, mode, pnl, timestamp, status_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    order["order_id"],
                    proposal_id,
                    order["instrument"],
                    order["type"],
                    order["quantity"],
                    order["price"],
                    order["status"],
                    order["mode"],
                    order.get("pnl"),
                    order["timestamp"],
                    order.get("status_message"),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get_history_from_db(limit: int = 50) -> list[dict[str, Any]]:
        """
        Retrieves unified history joining trade suggestions with linked position outcomes.
        """
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = """
            SELECT
                s.proposal_id,
                s.symbol,
                s.instrument,
                s.signal_type,
                s.direction,
                s.lot_size,
                s.entry_price,
                s.stop_loss,
                s.target_1,
                s.target_2,
                s.risk_reward,
                s.confidence,
                s.technical_rationale,
                s.status AS suggestion_status,
                s.created_at AS suggested_at,
                p.position_id,
                p.status AS position_status,
                p.buy_price,
                p.current_ltp,
                p.unrealized_pnl,
                p.realized_pnl,
                p.pnl_pct,
                p.exit_price,
                p.close_reason,
                p.opened_at,
                p.closed_at,
                p.mode
            FROM trade_suggestions s
            LEFT JOIN positions p ON s.proposal_id = p.proposal_id
            ORDER BY s.id DESC
            LIMIT ?
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()

            results = []
            for r in rows:
                item = dict(r)
                if item["position_status"] == "OPEN":
                    item["overall_status"] = "OPEN"
                elif item["position_status"] == "CLOSED":
                    item["overall_status"] = "CLOSED"
                elif item["suggestion_status"] == "APPROVED":
                    item["overall_status"] = "APPROVED"
                elif item["suggestion_status"] == "REJECTED":
                    item["overall_status"] = "REJECTED"
                else:
                    item["overall_status"] = "PENDING"
                results.append(item)

            return results
        finally:
            conn.close()


# ==================== BACKWARD COMPATIBLE PROCEDURAL FACADES ====================


def save_suggestion(proposal: dict[str, Any]) -> None:
    TradingRepository.save_suggestion(proposal)


def update_suggestion_status(proposal_id: str, status: str) -> None:
    TradingRepository.update_suggestion_status(proposal_id, status)


def save_position(pos: dict[str, Any]) -> None:
    TradingRepository.save_position(pos)


def update_position_in_db(pos: dict[str, Any]) -> None:
    TradingRepository.update_position_in_db(pos)


def update_position_pnl(position_id: str, current_ltp: float, unrealized_pnl: float, pnl_pct: float) -> None:
    TradingRepository.update_position_pnl(position_id, current_ltp, unrealized_pnl, pnl_pct)


def update_position_status(
    position_id: str, status: str, exit_price: float, realized_pnl: float, close_reason: str
) -> None:
    TradingRepository.update_position_status(position_id, status, exit_price, realized_pnl, close_reason)


def get_position_by_id(position_id: str) -> dict[str, Any] | None:
    return TradingRepository.get_position_by_id(position_id)


def get_open_positions_from_db() -> dict[str, dict[str, Any]]:
    return TradingRepository.get_open_positions_from_db()


def save_order(order: dict[str, Any], proposal_id: str | None = None) -> None:
    TradingRepository.save_order(order, proposal_id)


def get_closed_positions_on(date_prefix: str, mode: str) -> list[dict[str, Any]]:
    return TradingRepository.get_closed_positions_on(date_prefix, mode)


def get_history_from_db(limit: int = 50) -> list[dict[str, Any]]:
    return TradingRepository.get_history_from_db(limit)


# ==================== SECURE VAULT & AUTH MANAGEMENT ====================


def is_master_password_set() -> bool:
    """Checks whether the system has been initialized with a master password."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT is_initialized FROM auth_config WHERE id = 1")
        row = cursor.fetchone()
        return bool(row and row["is_initialized"] == 1)
    finally:
        conn.close()


def setup_master_password(password: str) -> None:
    """Sets initial master password and derives the master vault encryption key."""
    from app.core.security import derive_fernet_key, hash_password

    global _unlocked_encryption_key

    pwd_hash, salt_hex = hash_password(password)
    master_key_salt = os.urandom(16).hex()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
        INSERT OR REPLACE INTO auth_config (id, password_hash, salt, master_key_salt, is_initialized, created_at)
        VALUES (1, ?, ?, ?, 1, ?)
        """,
            (pwd_hash, salt_hex, master_key_salt, now),
        )
        conn.commit()
    finally:
        conn.close()

    _unlocked_encryption_key = derive_fernet_key(password, bytes.fromhex(master_key_salt))
    log_config_saved("database.setup_master_password", ["master_password_hash", "master_key_salt"])


def verify_and_unlock_master_password(password: str) -> bool:
    """Validates provided master password against PBKDF2 hash and unlocks the Fernet vault key."""
    from app.core.security import derive_fernet_key, verify_password

    global _unlocked_encryption_key

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash, salt, master_key_salt FROM auth_config WHERE id = 1")
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return False

    is_valid = verify_password(password, row["password_hash"], row["salt"])
    if is_valid:
        _unlocked_encryption_key = derive_fernet_key(password, bytes.fromhex(row["master_key_salt"]))
    return is_valid


def lock_vault() -> None:
    """Locks the secure vault by purging the encryption key from memory."""
    global _unlocked_encryption_key
    _unlocked_encryption_key = None


def is_vault_unlocked() -> bool:
    """Returns True if the vault is currently unlocked with the active encryption key."""
    return _unlocked_encryption_key is not None


def save_secure_setting(key: str, plain_value: str) -> None:
    """Encrypts a sensitive string using Fernet and stores it in SQLite secure_vault."""
    from app.core.security import encrypt_value

    global _unlocked_encryption_key
    if not _unlocked_encryption_key:
        raise RuntimeError("Vault is locked. Authenticate with master password first.")

    encrypted_text = encrypt_value(plain_value, _unlocked_encryption_key)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
        INSERT OR REPLACE INTO secure_vault (key, encrypted_value, updated_at)
        VALUES (?, ?, ?)
        """,
            (key, encrypted_text, now),
        )
        conn.commit()
    finally:
        conn.close()
    log_config_saved("database.save_secure_setting", [key])


def get_secure_setting(key: str, default: str = "") -> str:
    """Decrypts a sensitive setting from the vault using the in-memory master key."""
    from app.core.security import decrypt_value

    global _unlocked_encryption_key
    if not _unlocked_encryption_key:
        return default

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT encrypted_value FROM secure_vault WHERE key = ?", (key,))
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row or not row["encrypted_value"]:
        return default

    decrypted = decrypt_value(row["encrypted_value"], _unlocked_encryption_key)
    return decrypted if decrypted else default


def get_all_secure_settings() -> dict[str, str]:
    """Returns all settings with decrypted values for internal configurations."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT key FROM secure_vault")
        rows = cursor.fetchall()
    finally:
        conn.close()

    result = {}
    for r in rows:
        val = get_secure_setting(r["key"], "")
        result[r["key"]] = val
    return result


# Initialize database schema upon module loading
init_db()
