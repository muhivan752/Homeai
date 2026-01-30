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
    # CHECK constraints enforce valid enum values
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            event_type TEXT NOT NULL,
            category TEXT NOT NULL CHECK (category IN ('user', 'anomaly', 'emergency')),
            severity TEXT NOT NULL CHECK (severity IN ('debug', 'info', 'warning', 'critical', 'fatal')),
            source TEXT NOT NULL CHECK (source IN ('edge', 'backend', 'user', 'admin', 'system', 'external')),
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
    # CHECK constraints enforce valid enum values
    c.execute("""
        CREATE TABLE IF NOT EXISTS decision_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id TEXT UNIQUE NOT NULL,

            -- Link to trigger
            trigger_event_id TEXT NOT NULL,
            trigger_event_type TEXT NOT NULL,

            -- Decision details (constrained vocabulary)
            decision_type TEXT NOT NULL CHECK (decision_type IN (
                'alert_user', 'alert_family', 'call_emergency', 'disable_device',
                'lockdown', 'escalate', 'auto_recovery', 'no_action'
            )),
            action_taken TEXT NOT NULL,
            reason TEXT NOT NULL,

            -- Confidence & Model info
            confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
            model_name TEXT,
            model_version TEXT,

            -- Actor (who/what made the decision) - constrained
            actor_type TEXT NOT NULL CHECK (actor_type IN (
                'system', 'model', 'rule', 'user', 'admin', 'edge', 'external'
            )),
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
    # TRUSTED CONTACTS (For emergency alerts)
    # ===============================
    # Who to notify when emergency happens (not authorities)
    c.execute("""
        CREATE TABLE IF NOT EXISTS trusted_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            relationship TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            telegram_chat_id TEXT,

            -- Priority (lower = higher priority)
            priority INTEGER DEFAULT 1,

            -- What events to notify for
            notify_intrusion INTEGER DEFAULT 1,
            notify_fire INTEGER DEFAULT 1,
            notify_violence INTEGER DEFAULT 1,
            notify_emergency INTEGER DEFAULT 1,

            -- Status
            is_active INTEGER DEFAULT 1,
            verified_at INTEGER,

            created_at INTEGER NOT NULL,
            updated_at INTEGER,

            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_trusted_contacts_user
        ON trusted_contacts(user_id, priority)
    """)

    # ===============================
    # ESCALATION POLICIES (User-configurable rules)
    # ===============================
    # Defines HOW system should respond to each event type
    # This is the "policy-driven autonomy" - user explicitly delegates
    c.execute("""
        CREATE TABLE IF NOT EXISTS escalation_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN (
                'intrusion', 'fire', 'violence', 'water_leak', 'power_emergency', 'panic'
            )),

            -- Confirmation settings
            confirmation_required INTEGER DEFAULT 1,
            confirmation_window_seconds INTEGER DEFAULT 30,

            -- Auto-escalation thresholds
            auto_escalate_confidence REAL DEFAULT 0.95,
            auto_escalate_after_seconds INTEGER DEFAULT 30,

            -- What actions are allowed
            allow_local_alarm INTEGER DEFAULT 1,
            allow_alert_owner INTEGER DEFAULT 1,
            allow_alert_family INTEGER DEFAULT 1,
            allow_alert_trusted INTEGER DEFAULT 1,
            allow_call_authority INTEGER DEFAULT 0,
            allow_recording INTEGER DEFAULT 0,

            -- Authority settings (only if allow_call_authority = 1)
            authority_type TEXT,
            authority_number TEXT,

            -- Policy status
            is_active INTEGER DEFAULT 1,
            acknowledged_at INTEGER,

            created_at INTEGER NOT NULL,
            updated_at INTEGER,

            UNIQUE(user_id, event_type),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # ===============================
    # USER CONSENTS (Privacy & Recording)
    # ===============================
    # Explicit consent tracking - NO silent recording/escalation
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_consents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            consent_type TEXT NOT NULL CHECK (consent_type IN (
                'emergency_recording',
                'evidence_storage',
                'trusted_contact_alert',
                'authority_escalation',
                'data_retention',
                'terms_of_service',
                'privacy_policy',
                'system_limitations'
            )),

            -- Consent details
            granted INTEGER DEFAULT 0,
            granted_at INTEGER,
            revoked_at INTEGER,

            -- What was shown to user
            consent_version TEXT NOT NULL,
            consent_text_hash TEXT NOT NULL,

            -- How consent was given
            consent_method TEXT NOT NULL CHECK (consent_method IN (
                'checkbox', 'signature', 'voice', 'biometric'
            )),

            -- IP/device for audit
            ip_address TEXT,
            user_agent TEXT,

            created_at INTEGER NOT NULL,

            UNIQUE(user_id, consent_type),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # ===============================
    # PENDING CONFIRMATIONS (30-second window)
    # ===============================
    # Tracks events waiting for user confirmation before escalation
    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_confirmations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id TEXT NOT NULL,
            event_type TEXT NOT NULL,

            -- Confirmation window
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,

            -- What happens if no response
            fallback_action TEXT NOT NULL,

            -- Status
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                'pending', 'confirmed_safe', 'confirmed_threat', 'expired', 'cancelled'
            )),

            -- User response
            responded_at INTEGER,
            response_method TEXT,

            -- Escalation tracking
            escalated INTEGER DEFAULT 0,
            escalated_at INTEGER,
            escalation_decision_id TEXT,

            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (event_id) REFERENCES events(event_id)
        )
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_pending_confirmations_status
        ON pending_confirmations(status, expires_at)
    """)

    # ===============================
    # USER ACKNOWLEDGMENTS (Active consent flow)
    # ===============================
    # Tracks that user has actively acknowledged system limitations
    # This is NOT passive ToS - user must read and check each item
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_acknowledgments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,

            -- What was acknowledged
            ack_system_not_replacement INTEGER DEFAULT 0,
            ack_internet_dependency INTEGER DEFAULT 0,
            ack_false_positive_possible INTEGER DEFAULT 0,
            ack_evidence_not_court_proof INTEGER DEFAULT 0,
            ack_response_time_not_guaranteed INTEGER DEFAULT 0,

            -- Completion
            all_acknowledged INTEGER DEFAULT 0,
            acknowledged_at INTEGER,

            -- Version tracking
            acknowledgment_version TEXT NOT NULL,

            created_at INTEGER NOT NULL,

            UNIQUE(user_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # ===============================
    # COMPANION MODE: NOTIFICATION PREFERENCES
    # ===============================
    c.execute("""
        CREATE TABLE IF NOT EXISTS notification_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            preferences TEXT NOT NULL,  -- JSON blob with all settings
            created_at INTEGER NOT NULL,
            updated_at INTEGER,
            UNIQUE(user_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # ===============================
    # COMPANION MODE: NOTIFICATION LOG
    # ===============================
    # Tracks what was sent AND what was suppressed (for learning)
    c.execute("""
        CREATE TABLE IF NOT EXISTS notification_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            location TEXT,
            decision TEXT NOT NULL,  -- send, suppress_routine, etc.
            reason TEXT,
            message_sent INTEGER DEFAULT 0,
            user_response TEXT,  -- view, ignore, later, etc.
            response_at INTEGER,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # ===============================
    # COMPANION MODE: ACTIVITY BASELINE
    # ===============================
    # Passive learning of "normal" patterns
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_baseline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            location TEXT NOT NULL,
            day_of_week INTEGER,  -- 0=Monday, 6=Sunday
            hour_of_day INTEGER,  -- 0-23
            event_type TEXT NOT NULL,
            avg_count REAL DEFAULT 0,
            std_deviation REAL DEFAULT 0,
            sample_count INTEGER DEFAULT 0,
            last_updated INTEGER NOT NULL,
            UNIQUE(user_id, location, day_of_week, hour_of_day, event_type),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # ===============================
    # COMPANION MODE: KNOWN PERSONS (IDENTITY)
    # ===============================
    # Simple whitelist for Stage 1
    c.execute("""
        CREATE TABLE IF NOT EXISTS known_persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            relationship TEXT,  -- family, friend, helper, etc.
            photo_reference TEXT,  -- Path to reference photo
            is_child INTEGER DEFAULT 0,
            expected_schedule TEXT,  -- JSON: {"school_return": "15:30"}
            is_active INTEGER DEFAULT 1,
            created_at INTEGER NOT NULL,
            updated_at INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id)
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