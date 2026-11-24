import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fraudguard.db"))

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

@contextmanager
def get_db():
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('CUSTOMER', 'ADMIN')),
            is_active INTEGER NOT NULL DEFAULT 1,
            failed_login_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        
        # Password reset OTP table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_otps (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            otp_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts_left INTEGER NOT NULL DEFAULT 5,
            is_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)
        
        # Sessions / Refresh tokens table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            refresh_token_hash TEXT NOT NULL,
            user_agent TEXT,
            ip_address TEXT,
            expires_at TEXT NOT NULL,
            is_revoked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        # Audit logs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            action TEXT NOT NULL,
            ip_address TEXT,
            details TEXT,
            created_at TEXT NOT NULL
        );
        """)

        # Persisted simulated account balances
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            user_id TEXT UNIQUE NOT NULL,
            balance_cents INTEGER NOT NULL DEFAULT 1000000 CHECK(balance_cents >= 0),
            currency TEXT NOT NULL DEFAULT 'USD',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        # Transaction ledger and fraud decisions
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            recipient_id TEXT NOT NULL,
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            description TEXT,
            fraud_probability REAL,
            raw_fraud_probability REAL,
            scoring_latency_ms REAL,
            decision TEXT,
            model_version TEXT,
            status TEXT NOT NULL,
            risk_reasons TEXT,
            ml_features TEXT,
            sender_balance_before_cents INTEGER,
            sender_balance_after_cents INTEGER,
            recipient_balance_before_cents INTEGER,
            recipient_balance_after_cents INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (recipient_id) REFERENCES users(id),
            UNIQUE(sender_id, idempotency_key)
        );
        """)

        # Add scoring observability columns to databases created before Phase 3.
        transaction_columns = {
            row["name"] for row in cursor.execute("PRAGMA table_info(transactions)").fetchall()
        }
        for column, definition in (
            ("raw_fraud_probability", "REAL"),
            ("scoring_latency_ms", "REAL"),
        ):
            if column not in transaction_columns:
                cursor.execute(f"ALTER TABLE transactions ADD COLUMN {column} {definition}")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ledger_entries (
            id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            entry_type TEXT NOT NULL CHECK(entry_type IN ('DEBIT', 'CREDIT')),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            balance_before_cents INTEGER NOT NULL CHECK(balance_before_cents >= 0),
            balance_after_cents INTEGER NOT NULL CHECK(balance_after_cents >= 0),
            created_at TEXT NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id),
            UNIQUE(transaction_id, account_id, entry_type)
        );
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_otp_user ON password_reset_otps(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_sender ON transactions(sender_id, created_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_recipient ON transactions(recipient_id, created_at DESC);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status, created_at DESC);")

        # Provision accounts for existing customer rows.
        cursor.execute("""
            INSERT OR IGNORE INTO accounts (id, user_id, balance_cents, currency, created_at, updated_at)
            SELECT 'acct_' || substr(id, 5), id, 1000000, 'USD',
                   COALESCE(created_at, ?), COALESCE(updated_at, ?)
            FROM users
            WHERE role = 'CUSTOMER'
        """, (datetime.now().isoformat(), datetime.now().isoformat()))
