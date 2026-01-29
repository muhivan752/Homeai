# ===============================
# contracts/events.py — Edge → Backend Events (FINAL)
# ===============================

from dataclasses import dataclass
from typing import Optional, Literal


EventReason = Literal[
    "normal",
    "manual",
    "power_loss",
    "network_lost",
    "reboot",
    "unknown",
]


@dataclass(frozen=True)
class DeviceStateReported:
    """
    RUNTIME FACT:
    Edge reports actual device state.
    """
    event_id: str              # UUID / hash (idempotency)
    version: int               # contract version (start 1)

    device_id: int
    is_online: Literal["online", "offline"]

    reported_at: int           # unix timestamp (seconds)
    reason: EventReason = "unknown"


@dataclass(frozen=True)
class EnergyUsageReported:
    """
    SENSOR FACT:
    Raw energy sample from edge.
    """
    event_id: str              # UUID / hash
    version: int               # contract version (start 1)

    device_id: int
    watt: float
    measured_at: int           # unix timestamp (seconds)