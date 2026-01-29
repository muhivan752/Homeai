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