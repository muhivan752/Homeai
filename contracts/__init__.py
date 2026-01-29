# ===============================
# contracts/__init__.py - Edge Communication Contracts
# ===============================
# These contracts define the interface between Python (Brain) and Rust (Edge).
# 
# Communication Flow:
# 1. Python → Rust: Commands (ToggleDeviceCommand)
# 2. Rust → Python: Events (DeviceStateReported, EnergyUsageReported)
# 3. Shared State: DeviceState (desired_state owned by Python, is_online owned by Rust)

from contracts.commands import ToggleDeviceCommand, CommandSource, DeviceState as CommandDeviceState
from contracts.events import DeviceStateReported, EnergyUsageReported, EventReason
from contracts.states import DeviceState

__all__ = [
    # Commands (Python → Rust)
    'ToggleDeviceCommand',
    'CommandSource',
    
    # Events (Rust → Python)
    'DeviceStateReported',
    'EnergyUsageReported',
    'EventReason',
    
    # State
    'DeviceState',
]
