# ===============================
# routes/devices.py - Device Routes (PRODUCTION)
# ===============================
# ROLE: UI Adapter Only - NO business logic here
# All logic delegated to DeviceService

from flask import Blueprint, render_template, redirect, url_for, flash, g, current_app, request
from utils.decorators import login_required

devices_bp = Blueprint("devices", __name__, url_prefix="/devices")


def get_device_service():
    """Get DeviceService from app config."""
    return current_app.config["SERVICES"]["device"]


# ===============================
# DEVICE LIST
# ===============================

@devices_bp.route("/")
@login_required
def device_list():
    """Display all user's devices."""
    device_service = get_device_service()
    devices = device_service.get_user_devices(g.user["id"])
    
    # Count by status for UI
    stats = {
        'total': len(devices),
        'active': sum(1 for d in devices if d['status'] == 'active'),
        'pending': sum(1 for d in devices if d['status'] in ('pending_payment', 'pending_review')),
        'online': sum(1 for d in devices if d.get('is_online'))
    }
    
    return render_template("devices.html", devices=devices, stats=stats)


# ===============================
# DEVICE DETAIL
# ===============================

@devices_bp.route("/<int:device_id>")
@login_required
def device_detail(device_id):
    """Display single device details."""
    device_service = get_device_service()
    device = device_service.get_device(device_id, g.user["id"])
    
    if not device:
        flash("Device tidak ditemukan", "error")
        return redirect(url_for("devices.device_list"))
    
    # Get energy data if active
    energy_data = None
    if device['status'] == 'active':
        energy_service = current_app.config["SERVICES"]["energy"]
        energy_data = energy_service.get_device_readings(
            device_id, g.user["id"], limit=50
        )
    
    return render_template(
        "device_detail.html", 
        device=device,
        energy_data=energy_data
    )


# ===============================
# DEVICE COMMANDS
# ===============================

@devices_bp.route("/<int:device_id>/toggle", methods=["POST"])
@login_required
def toggle_device(device_id):
    """
    Toggle device state (on/off).
    This sets desired_state - Edge will execute.
    """
    device_service = get_device_service()
    
    try:
        result = device_service.request_toggle_device(
            device_id=device_id,
            user_id=g.user["id"],
        )
        flash(result["message"], "success")
    except ValueError as e:
        flash(str(e), "error")
    
    return redirect(url_for("devices.device_detail", device_id=device_id))


# ===============================
# DEVICE DISABLE
# ===============================

@devices_bp.route("/<int:device_id>/disable", methods=["POST"])
@login_required
def disable_device(device_id):
    """Disable/deactivate a device."""
    device_service = get_device_service()
    
    try:
        device_service.disable_device(
            device_id=device_id,
            user_id=g.user["id"],
        )
        flash("Device berhasil dinonaktifkan", "success")
    except ValueError as e:
        flash(str(e), "error")
    
    return redirect(url_for("devices.device_list"))


# ===============================
# DEVICE ADD (Optional - for future)
# ===============================

@devices_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_device():
    """Add new device."""
    if request.method == "POST":
        device_service = get_device_service()
        
        name = request.form.get("name", "").strip()
        device_type = request.form.get("device_type", "").strip()
        location = request.form.get("location", "").strip()
        power_watts = request.form.get("power_watts", 100, type=int)
        
        if not name:
            flash("Nama device harus diisi", "warning")
            return redirect(url_for("devices.add_device"))
        
        device_id = device_service.add_device(
            uid=g.user["id"],
            name=name,
            device_type=device_type or None,
            location=location or None,
            power_watts=power_watts
        )
        
        if device_id:
            flash("Device berhasil ditambahkan. Silakan lakukan pembayaran.", "success")
            return redirect(url_for("billing.billing"))
        else:
            flash("Gagal menambahkan device", "danger")
    
    return render_template("device_add.html")


# ===============================
# DEVICE DELETE
# ===============================

@devices_bp.route("/<int:device_id>/delete", methods=["POST"])
@login_required
def delete_device(device_id):
    """Delete a device."""
    device_service = get_device_service()
    
    # Only allow delete for non-active devices
    device = device_service.get_device(device_id, g.user["id"])
    if device and device['status'] == 'active':
        flash("Device aktif tidak bisa dihapus. Nonaktifkan terlebih dahulu.", "warning")
        return redirect(url_for("devices.device_detail", device_id=device_id))
    
    if device_service.delete_device(device_id, g.user["id"]):
        flash("Device berhasil dihapus", "success")
    else:
        flash("Gagal menghapus device", "danger")
    
    return redirect(url_for("devices.device_list"))
