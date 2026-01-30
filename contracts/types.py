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


class ActorType(str, Enum):
    """
    WHO/WHAT made a decision.

    Used in DecisionService to track decision source.
    """
    SYSTEM = "system"       # Automated system rule
    MODEL = "model"         # AI/ML model
    RULE = "rule"           # Business rule engine
    USER = "user"           # User override/manual
    ADMIN = "admin"         # Admin override
    EDGE = "edge"           # Edge device decision
    EXTERNAL = "external"   # External service


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
# ESCALATION TYPES
# ===============================

class EmergencyType(str, Enum):
    """
    Types of emergency events.

    Each type has different escalation policies.
    """
    INTRUSION = "intrusion"           # Unauthorized person detected
    FIRE = "fire"                     # Fire/smoke detected
    VIOLENCE = "violence"             # Violence detected (sensitive)
    WATER_LEAK = "water_leak"         # Water leak detected
    POWER_EMERGENCY = "power_emergency"  # Power system failure
    PANIC = "panic"                   # Panic button pressed


class EscalationAction(str, Enum):
    """
    Actions that can be taken during escalation.

    These are the building blocks of escalation policy.
    """
    LOCAL_ALARM = "local_alarm"           # Siren, lights
    ALERT_OWNER = "alert_owner"           # Notify primary user
    ALERT_FAMILY = "alert_family"         # Notify family members
    ALERT_TRUSTED = "alert_trusted"       # Notify trusted contacts
    CALL_POLICE = "call_police"           # Call police (requires consent)
    CALL_FIRE = "call_fire"               # Call fire department
    CALL_AMBULANCE = "call_ambulance"     # Call ambulance
    RECORD_EVIDENCE = "record_evidence"   # Start recording (requires consent)
    LOCKDOWN = "lockdown"                 # Lock all doors/windows
    DISABLE_DEVICE = "disable_device"     # Safety shutoff


class ConfirmationStatus(str, Enum):
    """
    Status of pending confirmation requests.
    """
    PENDING = "pending"               # Waiting for user response
    CONFIRMED_SAFE = "confirmed_safe" # User confirmed false alarm
    CONFIRMED_THREAT = "confirmed_threat"  # User confirmed real threat
    EXPIRED = "expired"               # No response within window
    CANCELLED = "cancelled"           # Cancelled by system


class ConsentType(str, Enum):
    """
    Types of user consent that can be granted/revoked.

    NO silent recording or escalation without explicit consent.
    """
    EMERGENCY_RECORDING = "emergency_recording"
    EVIDENCE_STORAGE = "evidence_storage"
    TRUSTED_CONTACT_ALERT = "trusted_contact_alert"
    AUTHORITY_ESCALATION = "authority_escalation"
    DATA_RETENTION = "data_retention"
    TERMS_OF_SERVICE = "terms_of_service"
    PRIVACY_POLICY = "privacy_policy"
    SYSTEM_LIMITATIONS = "system_limitations"


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

# ===============================
# ESCALATION POLICY DEFAULTS
# ===============================
# These are CONSERVATIVE defaults - user must opt-in for aggressive actions

# Default confirmation window (30 seconds as agreed)
DEFAULT_CONFIRMATION_WINDOW = 30

# Confidence threshold for auto-escalation (very high by default)
DEFAULT_AUTO_ESCALATE_CONFIDENCE = 0.95

# Default actions by emergency type (CONSERVATIVE)
DEFAULT_ESCALATION_ACTIONS = {
    EmergencyType.INTRUSION: {
        "immediate": [EscalationAction.LOCAL_ALARM, EscalationAction.ALERT_OWNER],
        "after_confirmation": [EscalationAction.ALERT_TRUSTED],
        "requires_consent": [EscalationAction.CALL_POLICE, EscalationAction.RECORD_EVIDENCE],
    },
    EmergencyType.FIRE: {
        "immediate": [EscalationAction.LOCAL_ALARM, EscalationAction.ALERT_OWNER, EscalationAction.ALERT_FAMILY],
        "after_confirmation": [EscalationAction.CALL_FIRE],
        "requires_consent": [EscalationAction.RECORD_EVIDENCE],
    },
    EmergencyType.VIOLENCE: {
        # SENSITIVE: Alert trusted humans, NOT authorities by default
        "immediate": [EscalationAction.ALERT_OWNER],
        "after_confirmation": [EscalationAction.ALERT_TRUSTED],
        "requires_consent": [EscalationAction.CALL_POLICE, EscalationAction.RECORD_EVIDENCE],
    },
    EmergencyType.WATER_LEAK: {
        "immediate": [EscalationAction.LOCAL_ALARM, EscalationAction.ALERT_OWNER],
        "after_confirmation": [EscalationAction.DISABLE_DEVICE],
        "requires_consent": [],
    },
    EmergencyType.POWER_EMERGENCY: {
        "immediate": [EscalationAction.LOCAL_ALARM, EscalationAction.ALERT_OWNER, EscalationAction.DISABLE_DEVICE],
        "after_confirmation": [],
        "requires_consent": [EscalationAction.CALL_FIRE],
    },
    EmergencyType.PANIC: {
        # Panic = user explicitly asking for help
        "immediate": [EscalationAction.LOCAL_ALARM, EscalationAction.ALERT_OWNER, EscalationAction.ALERT_TRUSTED],
        "after_confirmation": [],
        "requires_consent": [EscalationAction.CALL_POLICE],
    },
}

# Confidence thresholds for tiered escalation
CONFIDENCE_THRESHOLDS = {
    "low": 0.5,       # Alert only, no action
    "medium": 0.75,   # Local alarm + alert
    "high": 0.90,     # Full escalation minus authority
    "very_high": 0.95 # Auto-escalate even to authority (if consented)
}


# ===============================
# COMPANION MODE TYPES
# ===============================
# HomeAI Companion = Friend, not robot
# Default = SILENT, Offer > Push, User chooses

class CompanionEventType(str, Enum):
    """
    Event types for Companion Mode (non-emergency).

    These events follow the Inform → Offer → User Chooses pattern.
    Default behavior for most: SILENT unless unusual.
    """
    # === PRESENCE EVENTS ===
    FAMILY_ARRIVED = "family_arrived"           # Known family member home
    FAMILY_LEFT = "family_left"                 # Known family member left
    CHILD_ARRIVED = "child_arrived"             # Child home (special tracking)
    CHILD_LEFT = "child_left"                   # Child left
    GUEST_ARRIVED = "guest_arrived"             # Known guest/visitor
    UNKNOWN_PERSON = "unknown_person"           # Person not in whitelist

    # === ACTIVITY EVENTS ===
    MOTION_DETECTED = "motion_detected"         # General motion
    DOOR_OPENED = "door_opened"                 # Door opened
    DOOR_CLOSED = "door_closed"                 # Door closed
    DOORBELL_RING = "doorbell_ring"             # Doorbell pressed
    ACTIVITY_IN_ZONE = "activity_in_zone"       # Activity in specific zone
    UNUSUAL_ACTIVITY = "unusual_activity"       # Anomaly vs baseline

    # === DELIVERY EVENTS ===
    COURIER_ARRIVED = "courier_arrived"         # Delivery person at door
    PACKAGE_DELIVERED = "package_delivered"     # Package left
    PACKAGE_PICKED_UP = "package_picked_up"     # Package taken

    # === CHILD/PET EVENTS ===
    CHILD_CRYING = "child_crying"               # Audio: child crying
    CHILD_SLEEPING = "child_sleeping"           # Child asleep (never auto-notify)
    PET_ACTIVITY = "pet_activity"               # Pet detected

    # === ENVIRONMENTAL EVENTS ===
    TEMPERATURE_ANOMALY = "temperature_anomaly" # Unusual temperature
    HUMIDITY_ANOMALY = "humidity_anomaly"       # Unusual humidity
    AIR_QUALITY_POOR = "air_quality_poor"       # Poor air quality
    LOUD_NOISE = "loud_noise"                   # Unusual noise detected

    # === SYSTEM EVENTS ===
    DEVICE_OFFLINE = "device_offline"           # Sensor/device went offline
    DEVICE_ONLINE = "device_online"             # Sensor/device back online
    LOW_BATTERY = "low_battery"                 # Device battery low


class NotificationMode(str, Enum):
    """
    User preference for notification verbosity.

    Stage 1: Simple toggle between modes.
    """
    QUIETER = "quieter"           # Minimal notifications
    BALANCED = "balanced"         # Default - notify unusual only
    INFORMATIVE = "informative"   # More updates (still not spam)


class NotificationDecision(str, Enum):
    """
    Outcome of notification routing decision.

    Used for logging and learning.
    """
    SEND = "send"                 # Notification sent
    SUPPRESS_ROUTINE = "suppress_routine"     # Suppressed: routine activity
    SUPPRESS_QUIET_HOURS = "suppress_quiet_hours"  # Suppressed: quiet hours
    SUPPRESS_USER_PREF = "suppress_user_pref"      # Suppressed: user disabled
    SUPPRESS_DUPLICATE = "suppress_duplicate"      # Suppressed: too recent
    SUPPRESS_BASELINE = "suppress_baseline"        # Suppressed: matches baseline
    DEFER_DIGEST = "defer_digest"                  # Deferred to daily digest


class UserAction(str, Enum):
    """
    Actions user can take in response to notification.

    Companion pattern: User ALWAYS has choice.
    """
    VIEW = "view"           # Lihat - view camera/snapshot
    IGNORE = "ignore"       # Abaikan - dismiss notification
    LATER = "later"         # Nanti - remind later
    CALL = "call"           # Hubungi - call the person
    CHECK = "check"         # Cek - check status
    ADJUST = "adjust"       # Atur - adjust setting
    ACKNOWLEDGE = "ack"     # Acknowledge without action


# ===============================
# COMPANION MODE DEFAULTS
# ===============================

# Events that ALWAYS notify (regardless of mode)
ALWAYS_NOTIFY_EVENTS = frozenset({
    CompanionEventType.DOORBELL_RING,      # User expects to respond
    CompanionEventType.UNKNOWN_PERSON,     # Security concern
    CompanionEventType.CHILD_CRYING,       # Safety concern
})

# Events that NEVER auto-notify
NEVER_AUTO_NOTIFY_EVENTS = frozenset({
    CompanionEventType.CHILD_SLEEPING,     # Privacy
    CompanionEventType.DEVICE_ONLINE,      # Too noisy
})

# Events that notify only when user is away
NOTIFY_WHEN_AWAY_EVENTS = frozenset({
    CompanionEventType.MOTION_DETECTED,
    CompanionEventType.DOOR_OPENED,
    CompanionEventType.ACTIVITY_IN_ZONE,
    CompanionEventType.COURIER_ARRIVED,
    CompanionEventType.PACKAGE_DELIVERED,
})

# Events that notify only when unusual
NOTIFY_WHEN_UNUSUAL_EVENTS = frozenset({
    CompanionEventType.FAMILY_ARRIVED,     # Only if late
    CompanionEventType.FAMILY_LEFT,        # Only if unusual time
    CompanionEventType.CHILD_ARRIVED,      # Only if late
    CompanionEventType.CHILD_LEFT,         # Only if unusual
})

# Default quiet hours
DEFAULT_QUIET_HOURS_START = "23:00"
DEFAULT_QUIET_HOURS_END = "07:00"

# Duplicate suppression window (seconds)
DUPLICATE_SUPPRESSION_WINDOW = 300  # 5 minutes

# Baseline deviation threshold for "unusual"
BASELINE_DEVIATION_THRESHOLD = 0.3  # 30% deviation from normal
