# ===============================
# contracts/types.py — Core Event Types (Source of Truth)
# ===============================
# This file defines the CANONICAL types used across the entire system.
# Both UI and Backend MUST use these types - no string literals allowed.
#
# RULE: If you need a new event category or severity, ADD IT HERE.
#       Do NOT create ad-hoc strings elsewhere.

from enum import Enum, auto
from typing import Literal


class EventCategory(str, Enum):
    """
    FIRST-CLASS EVENT CLASSIFICATION

    Every event in the system MUST have one of these categories.
    This is enforced at the type level - no exceptions.

    Categories:
    - USER: Normal user-initiated actions (commands, requests)
    - ANOMALY: System-detected unusual patterns (may need attention)
    - EMERGENCY: Critical security/safety events (REQUIRES IMMEDIATE ACTION)

    CRITICAL RULES:
    1. EMERGENCY events are IMMUTABLE - once recorded, cannot be modified
    2. EMERGENCY events NEVER enter AI/ML training pipelines
    3. EMERGENCY events are stored with cryptographic integrity
    """
    USER = "user"
    ANOMALY = "anomaly"
    EMERGENCY = "emergency"


class EventSeverity(str, Enum):
    """
    SEVERITY LEVELS

    Orthogonal to category - indicates urgency of response.
    Used for UI prioritization and notification routing.
    """
    DEBUG = "debug"       # Development only, not shown in production
    INFO = "info"         # Normal operation, logged but not alerted
    WARNING = "warning"   # Attention needed, non-blocking notification
    CRITICAL = "critical" # Immediate attention, blocking notification
    FATAL = "fatal"       # System integrity at risk, full escalation


class EventSource(str, Enum):
    """
    WHERE the event originated.

    Important for audit trail and trust level determination.
    """
    EDGE = "edge"         # From Rust edge executor
    BACKEND = "backend"   # From Python brain
    USER = "user"         # Direct user action
    ADMIN = "admin"       # Admin action
    SYSTEM = "system"     # Automated system process
    EXTERNAL = "external" # External API/webhook


class DecisionType(str, Enum):
    """
    TYPES OF AUTOMATED DECISIONS

    Every time the system makes an autonomous decision,
    it must be categorized and logged.
    """
    ALERT_USER = "alert_user"           # Notify owner
    ALERT_FAMILY = "alert_family"       # Notify family members
    CALL_EMERGENCY = "call_emergency"   # Call emergency services
    DISABLE_DEVICE = "disable_device"   # Safety shutoff
    LOCKDOWN = "lockdown"               # Full system lockdown
    ESCALATE = "escalate"               # Escalate to higher authority
    AUTO_RECOVERY = "auto_recovery"     # Attempt automatic fix
    NO_ACTION = "no_action"             # Decided to take no action (logged anyway)


class EvidenceIntegrity(str, Enum):
    """
    INTEGRITY STATUS of stored evidence.

    For EMERGENCY events, evidence must be cryptographically verified.
    """
    UNVERIFIED = "unverified"   # Newly created, not yet hashed
    VERIFIED = "verified"       # Hash computed and stored
    TAMPERED = "tampered"       # Hash mismatch detected (CRITICAL!)
    ARCHIVED = "archived"       # Moved to cold storage, hash verified


# ===============================
# TYPE ALIASES for clarity
# ===============================

# Valid device states (shared vocabulary)
DeviceStateValue = Literal["on", "off"]
OnlineStatus = Literal["online", "offline"]

# Device workflow statuses
DeviceStatus = Literal[
    "pending_payment",
    "pending_review",
    "active",
    "rejected",
    "disabled"
]

# User roles
UserRole = Literal["user", "admin"]

# Subscription plans
PlanType = Literal["Basic", "Premium", "Enterprise"]


# ===============================
# POLICY CONSTANTS
# ===============================

# Events with these categories require immutable storage
IMMUTABLE_CATEGORIES = frozenset({EventCategory.EMERGENCY})

# Events with these severities trigger immediate notification
IMMEDIATE_NOTIFICATION_SEVERITIES = frozenset({
    EventSeverity.CRITICAL,
    EventSeverity.FATAL
})

# Maximum time (seconds) before emergency must be acknowledged
EMERGENCY_ACK_TIMEOUT = 300  # 5 minutes

# Evidence retention period (days)
EVIDENCE_RETENTION_DAYS = 365 * 7  # 7 years (legal requirement)
