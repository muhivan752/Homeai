# app.py — HomeAI Application Factory
# ROLE: CONTROL PLANE ONLY
# RULE: NO runtime loop / NO polling / NO edge logic

import os
from datetime import datetime

from flask import Flask, request, g, render_template, jsonify, redirect, flash
from flask_wtf import CSRFProtect

from config import Config, BASE_DIR
from database import init_db
from routes import register_blueprints
from utils.session import get_current_user
from services.container import init_services
from config import DATABASE_PATH

csrf = CSRFProtect()


def create_app():
    """
    Application Factory.
    SINGLE SOURCE OF TRUTH.
    """

    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, "templates"),
        static_folder=os.path.join(BASE_DIR, "static"),
    )

    # ===============================
    # CONFIG
    # ===============================
    app.config.from_object(Config)

    # ===============================
    # SECURITY
    # ===============================
    csrf.init_app(app)

    # ===============================
    # INIT CORE
    # ===============================
    with app.app_context():
        init_db()
    
    services = init_services(DATABASE_PATH)
    app.config["SERVICES"] = services
    
    register_blueprints(app)

    # ===============================
    # BEFORE REQUEST
    # ===============================
    @app.before_request
    def load_logged_in_user():
        if request.endpoint in ("static", "media.serve_media"):
            return
        if request.path.startswith("/static/") or request.path.startswith("/media/"):
            return
        g.user = get_current_user()

    # ===============================
    # ERROR HANDLERS
    # ===============================
    @app.errorhandler(404)
    def not_found(error):
        return render_template(
            "error.html",
            error="Halaman tidak ditemukan",
            code=404,
        ), 404

    @app.errorhandler(413)
    def too_large(error):
        return render_template(
            "error.html",
            error="File terlalu besar",
            code=413,
        ), 413

    @app.errorhandler(500)
    def internal_error(error):
        return render_template(
            "error.html",
            error="Terjadi kesalahan server",
            code=500,
        ), 500

    # ===============================
    # UTILITY ROUTES (OK UNTUK SEKARANG)
    # ===============================
    @app.route("/health")
    def health_check():
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
        }), 200

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

    @app.route("/connect/telegram")
    def connect_telegram():
        from utils.decorators import login_required
        from config import TELEGRAM_TOKEN

        @login_required
        def _connect():
            if not TELEGRAM_TOKEN:
                flash("Telegram integration belum dikonfigurasi", "warning")
                return redirect("/main/dashboard")

            return redirect(
                f"https://t.me/InforangueBot?start={g.user['id']}"
            )

        return _connect()

    return app