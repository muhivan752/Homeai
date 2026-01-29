# ===============================
# routes/api.py - API Endpoints (SECURE)
# ===============================

from flask import Blueprint, request, jsonify, g, current_app
from utils.decorators import login_required

api_bp = Blueprint('api', __name__, url_prefix='/api')


def get_services():
    return current_app.config["SERVICES"]


# ===============================
# EDGE / HARDWARE SENSOR UPDATE
# ===============================

@api_bp.route("/sensor/update", methods=["POST"])
def api_sensor_update():
    """
    Receive sensor data from EDGE / DEVICE
    AUTH: device_token (pre-shared)
    """
    services = get_services()
    data = request.get_json(silent=True) or {}

    device_id = data.get("device_id")
    device_token = data.get("device_token")
    watt = data.get("watt")
    measured_at = data.get("measured_at")

    if not device_id or not device_token or watt is None:
        return jsonify({"status": "invalid"}), 400

    try:
        # Validate device token
        device = services['device'].get_device_by_id(device_id)
        if not device or device.get("device_token") != device_token:
            return jsonify({"status": "unauthorized"}), 403

        services['energy'].log_sensor_data(
            device_id=device_id,
            watt=float(watt),
            measured_at=int(measured_at)
        )

        return jsonify({"status": "ok"}), 200

    except Exception:
        current_app.logger.exception("API SENSOR ERROR")
        return jsonify({"status": "error"}), 500


# ===============================
# USER ENERGY APIs
# ===============================

@api_bp.route("/energy/latest")
@login_required
def api_energy_latest():
    services = get_services()
    rows = services['energy'].get_latest_readings(
        g.user['id'],
        limit=20
    )
    return jsonify(rows)


@api_bp.route("/energy/daily")
@login_required
def api_energy_daily():
    services = get_services()
    days = request.args.get('days', 7, type=int)
    rows = services['energy'].get_daily_summary(
        g.user['id'],
        days=days
    )
    return jsonify(rows)


# ===============================
# USER DEVICE STATUS
# ===============================

@api_bp.route("/devices/status")
@login_required
def api_devices_status():
    services = get_services()
    devices = services['device'].get_user_devices(g.user['id'])
    return jsonify({
        "devices": devices,
        "total": len(devices),
    })