# ===============================
# routes/billing.py - Billing & Payment Routes (FIXED)
# ===============================

import os
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, g, current_app
from werkzeug.utils import secure_filename

from config import allowed_file
from utils.decorators import login_required

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')

# Pricing (MVP)
PRICE_BASIC = 99000
PRICE_ADDON = 20000


def get_services():
    return current_app.config["SERVICES"]


@billing_bp.route("/")
@login_required
def billing():
    services = get_services()
    devices = services['device'].get_user_devices(g.user['id'])

    pending_payment = [d for d in devices if d.get('status') == 'pending_payment']
    pending_review = [d for d in devices if d.get('status') == 'pending_review']
    active_devices = [d for d in devices if d.get('status') == 'active']
    rejected = [d for d in devices if d.get('status') == 'rejected']

    total_pending = sum(d.get('price', PRICE_ADDON) for d in pending_payment)

    return render_template(
        "billing.html",
        pending_payment=pending_payment,
        pending_review=pending_review,
        active_devices=active_devices,
        rejected=rejected,
        total_pending=total_pending,
        PRICE_BASIC=PRICE_BASIC,
        PRICE_ADDON=PRICE_ADDON
    )


@billing_bp.route("/upload", methods=["POST"])
@login_required
def upload_payment():
    services = get_services()

    file = request.files.get('proof')
    device_ids = request.form.getlist('device_ids')

    if not device_ids:
        single_id = request.form.get('device_id')
        if single_id:
            device_ids = [single_id]

    if not file or not file.filename:
        flash("File bukti pembayaran harus diupload", "warning")
        return redirect(url_for("billing.billing"))

    if not device_ids:
        flash("Pilih minimal satu perangkat", "warning")
        return redirect(url_for("billing.billing"))

    if not allowed_file(file.filename):
        flash("Format file tidak valid. Gunakan JPG, PNG, atau GIF.", "warning")
        return redirect(url_for("billing.billing"))

    filename = secure_filename(
        f"pay_{g.user['id']}_{int(datetime.now(timezone.utc).timestamp())}.jpg"
    )
    filepath = os.path.join(current_app.config['PAYMENT_FOLDER'], filename)

    try:
        file.save(filepath)

        success = services['device'].attach_payment_proof_bulk(
            device_ids=device_ids,
            user_id=g.user['id'],
            filename=filename
        )

        if success > 0:
            flash(
                f"✅ Bukti pembayaran untuk {success} perangkat berhasil diupload. "
                "Menunggu verifikasi admin (1x24 jam).",
                "success"
            )
        else:
            flash("Tidak ada perangkat yang bisa diproses", "warning")

    except Exception:
        current_app.logger.exception("Payment upload error")
        flash("Gagal upload bukti pembayaran", "danger")

    return redirect(url_for("billing.billing"))


@billing_bp.route("/resubmit/<int:device_id>", methods=["POST"])
@login_required
def resubmit_payment(device_id):
    services = get_services()
    result = services['device'].resubmit_payment(device_id, g.user['id'])

    if result:
        flash("Silakan upload ulang bukti pembayaran", "info")
    else:
        flash("Gagal mengubah status device", "danger")

    return redirect(url_for("billing.billing"))