# ===============================
# routes/admin.py - Admin Panel Routes (FIXED)
# ===============================

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, current_app
from utils.decorators import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def get_services():
    return current_app.config["SERVICES"]


@admin_bp.route("/users")
@admin_required
def admin_users():
    services = get_services()
    data = services['admin'].get_dashboard_data()
    return render_template("admin_user.html", **data)


@admin_bp.route("/user/<int:uid>")
@admin_required
def admin_user_detail(uid):
    services = get_services()
    user = services['admin'].get_user_detail(uid)
    if not user:
        flash("User tidak ditemukan", "danger")
        return redirect(url_for('admin.admin_users'))

    devices = services['device'].get_user_devices(uid)
    return render_template("admin_user_detail.html", user=user, devices=devices)


@admin_bp.route("/orders")
@admin_required
def admin_orders():
    services = get_services()
    orders = services['admin'].get_all_orders()

    stats = {
        'pending_payment': sum(1 for o in orders if o['status'] == 'pending_payment'),
        'pending_review': sum(1 for o in orders if o['status'] == 'pending_review'),
        'active': sum(1 for o in orders if o['status'] == 'active'),
        'rejected': sum(1 for o in orders if o['status'] == 'rejected'),
    }

    return render_template("admin_orders.html", orders=orders, stats=stats)


@admin_bp.route("/activate/<int:device_id>", methods=["POST"])
@admin_required
def activate_device(device_id):
    services = get_services()
    result = services['admin'].activate_device(device_id, admin_id=g.user['id'])

    if result:
        flash("✅ Device berhasil diaktivasi!", "success")
    else:
        flash("ℹ️ Device sudah diproses sebelumnya atau tidak valid", "warning")

    return redirect(url_for("admin.admin_orders"))


@admin_bp.route("/reject/<int:device_id>", methods=["POST"])
@admin_required
def reject_device(device_id):
    services = get_services()
    reason = request.form.get("reason", "Pembayaran tidak valid")
    result = services['admin'].reject_device(device_id, reason, admin_id=g.user['id'])

    if result:
        flash("Device ditolak. User akan diberitahu.", "warning")
    else:
        flash("ℹ️ Device sudah diproses sebelumnya atau tidak valid", "info")

    return redirect(url_for("admin.admin_orders"))


@admin_bp.route("/delete/<int:uid>", methods=["POST"])
@admin_required
def delete_user(uid):
    services = get_services()
    services['admin'].delete_user(uid, admin_id=g.user['id'])
    flash("User berhasil dinonaktifkan", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/update-plan", methods=["POST"])
@admin_required
def update_plan():
    services = get_services()
    uid = request.form.get("user_id")
    plan = request.form.get("plan")

    if not uid or not plan:
        flash("Data tidak lengkap", "danger")
        return redirect(url_for("admin.admin_users"))

    services['admin'].update_user_plan(uid, plan, admin_id=g.user['id'])
    flash("Plan user berhasil diupdate", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/sync")
@admin_required
def admin_sync():
    flash("Data berhasil di-refresh", "success")
    return redirect(url_for('admin.admin_users'))