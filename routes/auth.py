# ===============================
# routes/auth.py - Authentication Routes (FIXED)
# ===============================

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, session, flash, current_app
)

auth_bp = Blueprint('auth', __name__)


def get_services():
    return current_app.config["SERVICES"]


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Handle user login"""
    services = get_services()

    if request.method == "POST":
        email = request.form.get("email", "").lower().strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email dan password harus diisi", "warning")
            return redirect(url_for("auth.login"))

        user = services['user'].verify_login(email, password)
        if user:
            session.permanent = True
            session['user_id'] = user["id"]
            session['role'] = user["role"]
            flash(f"Selamat datang, {user['name']}!", "success")
            return redirect(url_for("main.dashboard"))

        flash("Email atau password salah", "danger")
        return redirect(url_for("auth.login"))

    return render_template("auth.html")


@auth_bp.route("/register", methods=["POST"])
def register():
    """Handle user registration"""
    services = get_services()

    name = request.form.get("nama", "").strip()
    email = request.form.get("email", "").lower().strip()
    password = request.form.get("password", "")

    if not name or not email or not password:
        flash("Semua field harus diisi", "danger")
        return redirect(url_for("auth.login"))

    if services['user'].email_exists(email):
        flash("Email sudah terdaftar", "danger")
        return redirect(url_for("auth.login"))

    user_id = services['user'].create_user(name, email, password)
    if user_id:
        flash("Registrasi berhasil! Silakan login.", "success")
    else:
        flash("Registrasi gagal. Coba lagi.", "danger")

    return redirect(url_for("auth.login"))


@auth_bp.route("/logout")
def logout():
    """Handle user logout"""
    session.clear()
    flash("Anda telah logout", "info")
    return redirect(url_for("main.index"))