# ===============================
# contracts/events.py — Event Definitions (Edge → Backend + System Events)
# ===============================
#
# ARCHITECTURE:
# - All events inherit from BaseEvent
# - All events MUST have a category (enforced by BaseEvent)
# - EMERGENCY events are automatically marked for immutable storage
# - Events are frozen (immutable) dataclasses

from dataclasses import dataclass, field
from typing import Optional, Literal, Any, Dict
import hashlib
import json
import time
import uuid

from contracts.types import (
    EventCategory,
    EventSeverity,
    EventSource,
    IMMUTABLE_CATEGORIES,
)


# ===============================
# EVENT REASON (Edge Reports)
# ===============================
EventReason = Literal[
    "normal",
    "manual",
    "power_loss",
    "network_lost",
    "reboot",
    "unknown",
]


# ===============================
# BASE EVENT CLASS
# ===============================
@dataclass(frozen=True)
class BaseEvent:
    """
    BASE CLASS FOR ALL EVENTS

    Every event in the system MUST inherit from this class.
    This enforces:
    1. Unique event_id for idempotency
    2. Mandatory category classification
    3. Severity level for routing
    4. Timestamp for ordering
    5. Source for audit trail
    6. Version for schema evolution

    RULES:
    - event_id: UUID, must be unique, used for deduplication
    - category: CANNOT be None, MUST be set
    - requires_immutable_storage: auto-computed based on category
    """
    # Identity
    event_id: str
    version: int = 1

    # Classification (MANDATORY)
    category: EventCategory = field(default=EventCategory.USER)
    severity: EventSeverity = field(default=EventSeverity.INFO)
    source: EventSource = field(default=EventSource.BACKEND)

    # Timing
    timestamp: int = field(default_factory=lambda: int(time.time()))

    # Metadata
    metadata: Optional[Dict[str, Any]] = None

    @property
    def requires_immutable_storage(self) -> bool:
        """Events in IMMUTABLE_CATEGORIES must be stored permanently."""
        return self.category in IMMUTABLE_CATEGORIES

    @property
    def event_type(self) -> str:
        """Returns the class name as event type."""
        return self.__class__.__name__

    def compute_hash(self) -> str:
        """
        Compute SHA-256 hash of event data for integrity verification.
        Used for EMERGENCY events to ensure evidence cannot be tampered.
        """
        # Create deterministic JSON representation
        data = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "version": self.version,
            "category": self.category.value,
            "severity": self.severity.value,
            "source": self.source.value,
            "timestamp": self.timestamp,
        }
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event to dictionary for storage/transmission."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "version": self.version,
            "category": self.category.value,
            "severity": self.severity.value,
            "source": self.source.value,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


# ===============================
# FACTORY FUNCTION
# ===============================
def generate_event_id() -> str:
    """Generate unique event ID (UUID v4)."""
    return str(uuid.uuid4())


# ===============================
# EDGE → BACKEND EVENTS (Runtime Facts)
# ===============================

@dataclass(frozen=True)
class DeviceStateReported(BaseEvent):
    """
    RUNTIME FACT:
    Edge reports actual device state.

    Category: USER (normal state change) or ANOMALY (unexpected offline)
    """
    device_id: int = 0
    is_online: Literal["online", "offline"] = "offline"
    reported_at: int = 0
    reason: EventReason = "unknown"

    # Override defaults for edge events
    source: EventSource = field(default=EventSource.EDGE)


@dataclass(frozen=True)
class EnergyUsageReported(BaseEvent):
    """
    SENSOR FACT:
    Raw energy sample from edge.

    Category: Always USER (routine data collection)
    """
    device_id: int = 0
    watt: float = 0.0
    measured_at: int = 0

    # Override defaults for edge events
    source: EventSource = field(default=EventSource.EDGE)


# ===============================
# ANOMALY EVENTS
# ===============================

@dataclass(frozen=True)
class AnomalyDetected(BaseEvent):
    """
    ANOMALY:
    System detected unusual pattern.

    Examples:
    - Energy spike beyond normal range
    - Device offline unexpectedly
    - Unusual access pattern
    """
    device_id: Optional[int] = None
    user_id: Optional[int] = None
    anomaly_type: str = "unknown"
    description: str = ""
    confidence: float = 0.0  # 0.0 - 1.0
    raw_data: Optional[Dict[str, Any]] = None

    # Anomalies default to WARNING severity
    category: EventCategory = field(default=EventCategory.ANOMALY)
    severity: EventSeverity = field(default=EventSeverity.WARNING)


@dataclass(frozen=True)
class EnergyAnomalyDetected(BaseEvent):
    """
    ANOMALY:
    Energy consumption outside normal bounds.
    """
    device_id: int = 0
    user_id: int = 0
    expected_watt: float = 0.0
    actual_watt: float = 0.0
    deviation_percent: float = 0.0
    window_start: int = 0
    window_end: int = 0

    category: EventCategory = field(default=EventCategory.ANOMALY)
    severity: EventSeverity = field(default=EventSeverity.WARNING)
    source: EventSource = field(default=EventSource.BACKEND)


# ===============================
# EMERGENCY EVENTS
# ===============================

@dataclass(frozen=True)
class EmergencyEvent(BaseEvent):
    """
    BASE EMERGENCY EVENT

    ALL emergency events MUST inherit from this.
    These events:
    1. Are stored immutably (append-only, with hash)
    2. NEVER enter AI/ML training pipelines
    3. Trigger immediate notification escalation
    4. Are retained for legal compliance (7+ years)
    """
    category: EventCategory = field(default=EventCategory.EMERGENCY)
    severity: EventSeverity = field(default=EventSeverity.CRITICAL)

    # Evidence fields
    raw_evidence: Optional[bytes] = None  # Video frame, audio clip, etc.
    evidence_hash: Optional[str] = None   # SHA-256 of raw_evidence
    evidence_type: Optional[str] = None   # "video", "audio", "image", "sensor"


@dataclass(frozen=True)
class IntrusionDetected(EmergencyEvent):
    """
    EMERGENCY:
    Unauthorized person detected in secured area.
    """
    user_id: int = 0
    location: str = ""
    camera_id: Optional[int] = None
    detection_confidence: float = 0.0
    face_match_result: Optional[str] = None  # "unknown", "family", "blocked"
    snapshot_path: Optional[str] = None

    severity: EventSeverity = field(default=EventSeverity.FATAL)


@dataclass(frozen=True)
class FireDetected(EmergencyEvent):
    """
    EMERGENCY:
    Fire or smoke detected.
    """
    user_id: int = 0
    location: str = ""
    sensor_id: Optional[int] = None
    smoke_level: Optional[float] = None
    temperature: Optional[float] = None
    detection_confidence: float = 0.0

    severity: EventSeverity = field(default=EventSeverity.FATAL)


@dataclass(frozen=True)
class WaterLeakDetected(EmergencyEvent):
    """
    EMERGENCY:
    Water leak detected.
    """
    user_id: int = 0
    location: str = ""
    sensor_id: Optional[int] = None
    water_level: Optional[float] = None
    detection_confidence: float = 0.0

    severity: EventSeverity = field(default=EventSeverity.CRITICAL)


@dataclass(frozen=True)
class PowerEmergency(EmergencyEvent):
    """
    EMERGENCY:
    Critical power system failure.
    """
    user_id: int = 0
    device_id: Optional[int] = None
    failure_type: str = ""  # "overload", "short_circuit", "surge", "failure"
    affected_circuits: Optional[list] = None

    severity: EventSeverity = field(default=EventSeverity.FATAL)


@dataclass(frozen=True)
class PanicButtonPressed(EmergencyEvent):
    """
    EMERGENCY:
    User pressed panic button.
    """
    user_id: int = 0
    family_member_id: Optional[int] = None
    location: Optional[str] = None
    button_type: str = "manual"  # "manual", "voice", "gesture"

    severity: EventSeverity = field(default=EventSeverity.FATAL)


# ===============================
# USER ACTION EVENTS
# ===============================

@dataclass(frozen=True)
class UserCommandReceived(BaseEvent):
    """
    USER:
    User issued a command via UI/voice/etc.
    """
    user_id: int = 0
    command_type: str = ""
    target_device_id: Optional[int] = None
    parameters: Optional[Dict[str, Any]] = None
    input_method: str = "ui"  # "ui", "voice", "api", "telegram"

    category: EventCategory = field(default=EventCategory.USER)
    source: EventSource = field(default=EventSource.USER)


@dataclass(frozen=True)
class DeviceToggleRequested(BaseEvent):
    """
    USER:
    User requested device state change.
    """
    user_id: int = 0
    device_id: int = 0
    requested_state: Literal["on", "off"] = "off"

    category: EventCategory = field(default=EventCategory.USER)
    source: EventSource = field(default=EventSource.USER)
