# ===============================
# routes/main.py - Main Routes (Dashboard, Profile)
# ===============================

import os
from datetime import datetime
from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, g, current_app
)
from werkzeug.utils import secure_filename

from config import TARIF_PLN_PER_KWH, allowed_file
from utils.decorators import login_required

main_bp = Blueprint('main', __name__)


def get_services():
    return current_app.config["SERVICES"]


@main_bp.route("/")
def index():
    """Landing page or redirect to dashboard if logged in"""
    if g.user:
        return redirect(url_for("main.dashboard"))
    return render_template("landing.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    """User dashboard (CONTROL PLANE ONLY)"""
    services = get_services()
    devs = services['device'].get_user_devices(g.user['id'])

    # CONTROL PLANE STATS (NO RUNTIME DEPENDENCY)
    total_devices = len(devs)
    active_devices = sum(1 for d in devs if d['status'] == 'active')

    stats = {
        "total": total_devices,
        "active": active_devices,
        "watts": None,
        "kwh": None,
        "cost": None,
    }

    return render_template(
        "dashboard.html",
        devices=devs,
        stats=stats
    )


@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """User profile page with avatar upload"""
    services = get_services()

    if request.method == "POST":
        file = request.files.get("avatar")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Format file tidak didukung", "warning")
                return redirect(url_for("main.profile"))

            timestamp = int(datetime.utcnow().timestamp())
            filename = secure_filename(
                f"user_{g.user['id']}_{timestamp}.jpg"
            )
            filepath = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                filename
            )

            try:
                file.save(filepath)
                services['user'].update_avatar(g.user['id'], filename)
                flash("Avatar berhasil diupdate!", "success")
            except Exception:
                current_app.logger.exception("Avatar upload failed")
                flash("Gagal upload avatar", "danger")

        return redirect(url_for("main.profile"))

    family = services['user'].get_family_members(g.user['id'])
    return render_template(
        "profile.html",
        user=g.user,
        family=family
    )


@main_bp.route("/profile/family/add", methods=["POST"])
@login_required
def add_family():
    """Add family member with optional photo"""
    services = get_services()

    name = request.form.get("name", "").strip()
    role = request.form.get("role", "").strip()

    if not name:
        flash("Nama anggota keluarga harus diisi", "warning")
        return redirect(url_for("main.profile"))

    photo_filename = "default.jpg"
    file = request.files.get("photo")

    if file and file.filename and allowed_file(file.filename):
        timestamp = int(datetime.utcnow().timestamp())
        photo_filename = secure_filename(
            f"face_{g.user['id']}_{timestamp}.jpg"
        )
        filepath = os.path.join(
            current_app.config['FACES_FOLDER'],
            photo_filename
        )
        try:
            file.save(filepath)
        except Exception:
            current_app.logger.exception("Family photo upload failed")
            flash("Gagal upload foto", "danger")
            return redirect(url_for("main.profile"))

    services['user'].add_family_member(
        g.user['id'],
        name,
        role,
        photo_filename
    )
    flash("Anggota keluarga berhasil ditambahkan", "success")
    return redirect(url_for("main.profile"))


@main_bp.route("/profile/family/delete/<int:member_id>", methods=["POST"])
@login_required
def delete_family(member_id):
    """Delete family member"""
    services = get_services()
    services['user'].delete_family_member(member_id, g.user['id'])
    flash("Anggota keluarga berhasil dihapus", "success")
    return redirect(url_for("main.profile"))


@main_bp.route("/devices")
@login_required
def devices_redirect():
    """Redirect to devices blueprint"""
    return redirect(url_for("devices.device_list"))