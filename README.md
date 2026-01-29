# HomeAI Backend (Python)

Production-ready backend for HomeAI smart home automation system.

## Architecture

```
Python (Brain/Otak)          Rust (Edge/Muscle)
├── User Management          ├── Real-time sensor polling
├── Authentication           ├── Device state management
├── Billing & Subscription   ├── GPIO control
├── Admin Panel              ├── Camera capture
├── Face Recognition/ML      └── Local buffering
├── Decision Making
└── API for Mobile App
       ↑
       │ HTTP/gRPC
       ↓
    [Contracts]
    ├── commands.py (Python → Rust)
    ├── events.py (Rust → Python)
    └── states.py (Shared)
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your SECRET_KEY

# 3. Run
./run.sh
# Or: python main.py
```

## Project Structure

```
homeai-fixed/
├── main.py              # Entry point
├── app.py               # Flask app factory
├── config.py            # Configuration
├── database.py          # Database initialization
├── services/            # Business logic layer
│   ├── base.py          # Base service with DB operations
│   ├── user.py          # Auth, profile, family
│   ├── device.py        # Device CRUD, state management
│   ├── energy.py        # Energy logging & analytics
│   ├── admin.py         # Admin operations
│   └── container.py     # Service initialization
├── routes/              # HTTP route handlers
│   ├── auth.py          # Login, register, logout
│   ├── main.py          # Dashboard, profile
│   ├── devices.py       # Device management
│   ├── billing.py       # Payment processing
│   ├── admin.py         # Admin panel
│   ├── api.py           # Edge API endpoints
│   └── media.py         # Secure media serving
├── contracts/           # Python ↔ Rust contracts
│   ├── commands.py      # Backend → Edge
│   ├── events.py        # Edge → Backend
│   └── states.py        # Shared state
├── templates/           # Jinja2 HTML templates
└── utils/               # Helpers & decorators
```

## API Endpoints for Edge (Rust)

### POST /api/sensor/update
Receive sensor data from Edge.

```json
{
  "device_id": 1,
  "device_token": "xxx",
  "watt": 85.5,
  "measured_at": 1706500000
}
```

### GET /api/energy/latest
Get latest energy readings (requires auth).

### GET /api/energy/daily
Get daily summary (requires auth).

### GET /api/devices/status
Get all devices status (requires auth).

## Services API

```python
from services import init_services

services = init_services(DATABASE_PATH)

# User operations
user = services['user'].verify_login(email, password)
services['user'].create_user(name, email, password)

# Device operations
devices = services['device'].get_user_devices(user_id)
services['device'].request_toggle_device(device_id, user_id)

# Energy operations
services['energy'].log_sensor_data(device_id, watt, measured_at)
readings = services['energy'].get_latest_readings(user_id)

# Admin operations
data = services['admin'].get_dashboard_data()
services['admin'].activate_device(device_id, admin_id)
```

## Testing

```bash
python test_services_standalone.py
```

## Control Plane vs Data Plane

- **desired_state**: Backend-owned intent (what user wants)
- **is_online**: Edge-owned fact (actual device state)

Backend only sets `desired_state`. Edge reports `is_online` via API.
