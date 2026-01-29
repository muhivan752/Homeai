# ===============================
# contracts/states.py — Logical Device State (FINAL)
# ===============================

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class DeviceState:
    """
    SOURCE OF TRUTH (BACKEND OWNED)
    - desired_state: intent (backend)
    - is_online: runtime fact (edge)
    """

    # Meta
    version: int                   # contract version
    device_id: int
    last_event_id: Optional[str]   # last applied edge event
    last_updated: int              # unix timestamp

    # BACKEND OWNED (INTENT)
    desired_state: Literal["on", "off"]

    # EDGE OWNED (FACT)
    is_online: Literal["online", "offline"]

    # Diagnostics
    last_error: Optional[str] = None