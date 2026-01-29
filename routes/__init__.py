# ===============================
# routes/__init__.py - Blueprint Registration (PRODUCTION)
# ===============================

from routes.auth import auth_bp
from routes.main import main_bp
from routes.devices import devices_bp
from routes.billing import billing_bp
from routes.admin import admin_bp
from routes.api import api_bp
from routes.media import media_bp


def register_blueprints(app):
    """
    Register all blueprints to the Flask app.
    
    Blueprint URL prefixes:
    - auth_bp: / (login, register, logout)
    - main_bp: / (index, dashboard, profile)
    - devices_bp: /devices
    - billing_bp: /billing
    - admin_bp: /admin
    - api_bp: /api
    - media_bp: /media
    """
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(devices_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(media_bp)
    
    print("✅ All blueprints registered")


__all__ = [
    'auth_bp',
    'main_bp',
    'devices_bp',
    'billing_bp',
    'admin_bp',
    'api_bp',
    'media_bp',
    'register_blueprints'
]
