# ===============================
# utils/decorators.py - Route Decorators (FINAL)
# ===============================

import functools
from flask import g, flash, redirect, url_for, request, abort


def _is_api_request():
    """
    Detect API / edge request.
    """
    return (
        request.path.startswith("/api")
        or request.headers.get("Accept") == "application/json"
    )


def login_required(f):
    """
    Require authenticated user.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = getattr(g, "user", None)
        if not user:
            if _is_api_request():
                abort(401)
            flash("Silakan login terlebih dahulu", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """
    Require admin role.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = getattr(g, "user", None)
        if not user or user.get("role") != "admin":
            if _is_api_request():
                abort(403)
            flash("Akses ditolak. Admin only.", "danger")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)
    return decorated


def verified_required(f):
    """
    Require verified user.
    Assumes missing 'verified' field = NOT verified.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = getattr(g, "user", None)
        if not user:
            if _is_api_request():
                abort(401)
            flash("Silakan login terlebih dahulu", "warning")
            return redirect(url_for("auth.login"))

        if not user.get("verified", False):
            if _is_api_request():
                abort(403)
            flash("Akun Anda belum terverifikasi", "warning")
            return redirect(url_for("main.profile"))

        return f(*args, **kwargs)
    return decorated