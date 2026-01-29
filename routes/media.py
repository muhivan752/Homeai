# ===============================
# routes/media.py — Secure Media Delivery (FINAL)
# ===============================

import os
from flask import (
    Blueprint,
    send_from_directory,
    abort,
    current_app,
    g,
)
from werkzeug.utils import secure_filename

from utils.decorators import login_required
from config import MEDIA_DIR, allowed_file

media_bp = Blueprint("media", __name__)

# ===============================
# CONFIG
# ===============================

PUBLIC_DIR = "avatars"
PRIVATE_DIRS = {"faces", "payments", "family"}


# ===============================
# HELPERS
# ===============================

def resolve_media_path(subdir: str, filename: str):
    base_path = os.path.join(MEDIA_DIR, subdir)
    file_path = os.path.join(base_path, filename)

    if not os.path.exists(file_path):
        return None

    return base_path, filename


def user_owns_file(category: str, filename: str, user_id: int) -> bool:
    """
    Ownership check based on DB record.
    """
    services = current_app.config["SERVICES"]

    if category == "faces":
        return services['user'].family_photo_belongs_to_user(filename, user_id)

    if category == "payments":
        return services['device'].payment_file_belongs_to_user(filename, user_id)

    if category == "family":
        return services['user'].family_photo_belongs_to_user(filename, user_id)

    return False


# ===============================
# PUBLIC MEDIA
# ===============================

@media_bp.route("/media/avatars/<filename>")
def serve_avatar(filename):
    filename = secure_filename(filename)

    if not allowed_file(filename):
        abort(404)

    resolved = resolve_media_path(PUBLIC_DIR, filename)
    if not resolved:
        abort(404)

    base_path, fname = resolved
    return send_from_directory(base_path, fname)


# ===============================
# PRIVATE MEDIA (AUTH REQUIRED)
# ===============================

@media_bp.route("/media/private/<category>/<filename>")
@login_required
def serve_private_media(category, filename):
    if category not in PRIVATE_DIRS:
        abort(404)

    filename = secure_filename(filename)

    if not allowed_file(filename):
        abort(404)

    # OWNERSHIP CHECK
    if not user_owns_file(category, filename, g.user['id']):
        abort(403)

    resolved = resolve_media_path(category, filename)
    if not resolved:
        abort(404)

    base_path, fname = resolved
    return send_from_directory(base_path, fname)