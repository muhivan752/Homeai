# ===============================
# contracts/__init__.py - Edge Communication Contracts
# ===============================
# These contracts define the interface between Python (Brain) and Rust (Edge).
#
# Communication Flow:
# 1. Python → Rust: Commands (ToggleDeviceCommand)
# 2. Rust → Python: Events (DeviceStateReported, EnergyUsageReported)
# 3. Shared State: DeviceState (desired_state owned by Python, is_online owned by Rust)
#
# Event Architecture:
# - All events inherit from BaseEvent
# - Events are classified by EventCategory (USER, ANOMALY, EMERGENCY)
# - EMERGENCY events require immutable storage with integrity verification

# Core Types (Source of Truth)
from contracts.types import (
    EventCategory,
    EventSeverity,
    EventSource,
    DecisionType,
    ActorType,
    EvidenceIntegrity,
    DeviceStateValue,
    OnlineStatus,
    DeviceStatus,
    UserRole,
    PlanType,
    IMMUTABLE_CATEGORIES,
    IMMEDIATE_NOTIFICATION_SEVERITIES,
    EMERGENCY_ACK_TIMEOUT,
    EVIDENCE_RETENTION_DAYS,
)

# Commands (Python → Rust)
from contracts.commands import (
    ToggleDeviceCommand,
    CommandSource,
    DeviceState as CommandDeviceState,
)

# Events (Rust → Python + System Events)
from contracts.events import (
    # Base
    BaseEvent,
    generate_event_id,
    EventReason,

    # Edge Events
    DeviceStateReported,
    EnergyUsageReported,

    # Anomaly Events
    AnomalyDetected,
    EnergyAnomalyDetected,

    # Emergency Events
    EmergencyEvent,
    IntrusionDetected,
    FireDetected,
    WaterLeakDetected,
    PowerEmergency,
    PanicButtonPressed,

    # User Events
    UserCommandReceived,
    DeviceToggleRequested,
)

# State
from contracts.states import DeviceState

__all__ = [
    # ===== Core Types =====
    'EventCategory',
    'EventSeverity',
    'EventSource',
    'DecisionType',
    'ActorType',
    'EvidenceIntegrity',
    'DeviceStateValue',
    'OnlineStatus',
    'DeviceStatus',
    'UserRole',
    'PlanType',

    # Policy Constants
    'IMMUTABLE_CATEGORIES',
    'IMMEDIATE_NOTIFICATION_SEVERITIES',
    'EMERGENCY_ACK_TIMEOUT',
    'EVIDENCE_RETENTION_DAYS',

    # ===== Commands (Python → Rust) =====
    'ToggleDeviceCommand',
    'CommandSource',
    'CommandDeviceState',

    # ===== Events =====
    # Base
    'BaseEvent',
    'generate_event_id',
    'EventReason',

    # Edge Events (Rust → Python)
    'DeviceStateReported',
    'EnergyUsageReported',

    # Anomaly Events
    'AnomalyDetected',
    'EnergyAnomalyDetected',

    # Emergency Events
    'EmergencyEvent',
    'IntrusionDetected',
    'FireDetected',
    'WaterLeakDetected',
    'PowerEmergency',
    'PanicButtonPressed',

    # User Events
    'UserCommandReceived',
    'DeviceToggleRequested',

    # ===== State =====
    'DeviceState',
]
