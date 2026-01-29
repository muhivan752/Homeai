# ===============================
# database.py - Database Initialization (FINAL)
# ===============================

import sqlite3
from config import DATABASE_PATH


def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    c = conn.cursor()

    # ===============================
    # USERS
    # ===============================
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            plan_name TEXT DEFAULT 'Basic',
            avatar TEXT,
            verified INTEGER DEFAULT 1,
            is_deleted INTEGER DEFAULT 0,
            telegram_chat_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ===============================
    # DEVICES
    # ===============================
    c.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            device_type TEXT,
            location TEXT,
            power_watts INTEGER DEFAULT 100,

            -- CONTROL PLANE
            status TEXT DEFAULT 'pending_review',
            desired_state INTEGER DEFAULT 0,

            -- RUNTIME (EDGE OWNED)
            is_online INTEGER DEFAULT 0,

            -- BILLING / REVIEW
            payment_proof TEXT,
            payment_date TIMESTAMP,
            activated_at TIMESTAMP,
            activated_by INTEGER,
            reject_reason TEXT,
            price INTEGER DEFAULT 20000,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ===============================
    # FAMILY MEMBERS
    # ===============================
    c.execute("""
        CREATE TABLE IF NOT EXISTS family_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            role TEXT,
            photo_identity TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ===============================
    # ENERGY LOGS (EDGE REPORT)
    # ===============================
    c.execute("""
        CREATE TABLE IF NOT EXISTS energy_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            watt REAL NOT NULL,
            measured_at INTEGER NOT NULL
        )
    """)

    # ===============================
    # SUBSCRIPTIONS
    # ===============================
    c.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_type TEXT DEFAULT 'basic',
            price INTEGER DEFAULT 99000,
            status TEXT DEFAULT 'pending',
            payment_proof TEXT,
            payment_date TIMESTAMP,
            start_date TIMESTAMP,
            end_date TIMESTAMP,
            activated_at TIMESTAMP,
            activated_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ===============================
    # ADMIN AUDIT LOG
    # ===============================
    c.execute("""
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)

    # ===============================
    # EVENT STORE (All Events)
    # ===============================
    # Central event log - all events pass through here
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            event_type TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            source TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            payload TEXT NOT NULL,
            created_at INTEGER NOT NULL,

            -- Indexing
            user_id INTEGER,
            device_id INTEGER
        )
    """)

    # Index for fast lookup by category and time
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_category_time
        ON events(category, created_at DESC)
    """)

    # Index for user-specific events
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_user
        ON events(user_id, created_at DESC)
    """)

    # ===============================
    # EVENT EVIDENCE (Immutable - EMERGENCY Only)
    # ===============================
    # CRITICAL: This table is APPEND-ONLY for legal compliance
    # - No UPDATE allowed
    # - No DELETE allowed (except by retention policy after 7 years)
    # - All records have integrity hash
    c.execute("""
        CREATE TABLE IF NOT EXISTS event_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            event_type TEXT NOT NULL,
            category TEXT NOT NULL CHECK (category = 'emergency'),

            -- Evidence Data
            payload TEXT NOT NULL,
            raw_evidence BLOB,
            evidence_type TEXT,

            -- Integrity
            integrity_hash TEXT NOT NULL,
            integrity_status TEXT DEFAULT 'verified',

            -- Immutability markers
            created_at INTEGER NOT NULL,
            is_immutable INTEGER DEFAULT 1,

            -- Retention
            retention_until INTEGER NOT NULL,
            archived_at INTEGER,
            archive_location TEXT,

            -- Foreign key to main events table
            FOREIGN KEY (event_id) REFERENCES events(event_id)
        )
    """)

    # No UPDATE trigger - enforce immutability at application level
    # (SQLite triggers for true immutability would be added in production)

    # ===============================
    # DECISION RECORDS (AI/Automation Decisions)
    # ===============================
    # Every automated decision must be logged here
    # "Why did the system decide X?" must be answerable
    c.execute("""
        CREATE TABLE IF NOT EXISTS decision_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id TEXT UNIQUE NOT NULL,

            -- Link to trigger
            trigger_event_id TEXT NOT NULL,
            trigger_event_type TEXT NOT NULL,

            -- Decision details
            decision_type TEXT NOT NULL,
            action_taken TEXT NOT NULL,
            reason TEXT NOT NULL,

            -- Confidence & Model info
            confidence REAL,
            model_name TEXT,
            model_version TEXT,

            -- Actor (who/what made the decision)
            actor_type TEXT NOT NULL,
            actor_id INTEGER,

            -- Outcome tracking
            outcome TEXT,
            outcome_at INTEGER,

            -- Timing
            created_at INTEGER NOT NULL,

            -- Foreign key
            FOREIGN KEY (trigger_event_id) REFERENCES events(event_id)
        )
    """)

    # Index for finding decisions by event
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_decisions_trigger
        ON decision_records(trigger_event_id)
    """)

    # Index for decision audit by type
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_decisions_type_time
        ON decision_records(decision_type, created_at DESC)
    """)

    # ===============================
    # SEED DEFAULT ADMIN (if not exists)
    # ===============================
    from werkzeug.security import generate_password_hash

    # Check if admin exists
    c.execute("SELECT id FROM users WHERE email = ?", ("admin@homeai.local",))
    if not c.fetchone():
        admin_password = generate_password_hash("admin123")
        c.execute("""
            INSERT INTO users (name, email, password, role, plan_name, verified)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("Administrator", "admin@homeai.local", admin_password, "admin", "Premium", 1))
        print("Default admin created: admin@homeai.local / admin123")

    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def check_db_connection():
    try:
        conn = sqlite3.connect(DATABASE_PATH, timeout=5.0)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False