# ===============================
# contracts/commands.py — Edge Command Contracts (FINAL)
# ===============================

from dataclasses import dataclass
from typing import Literal


CommandSource = Literal["user", "admin", "system", "recovery"]
DeviceState = Literal["on", "off"]


@dataclass(frozen=True)
class ToggleDeviceCommand:
    """
    EDGE COMMAND CONTRACT

    - Backend issues intent only
    - Edge decides execution
    - Must be idempotent
    """

    # Meta
    command_id: str          # UUID / hash (idempotency key)
    version: int             # contract version (start with 1)
    source: CommandSource    # who issued this command

    # Target
    device_id: int
    desired_state: DeviceState  # "on" | "off"

    # Timing
    issued_at: int           # unix timestamp (seconds)
    expires_at: int          # unix timestamp (drop if expired)