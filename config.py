# ===============================
# config.py - Konfigurasi HomeAI (HARDENED)
# ===============================

import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

# ===============================
# SECURITY
# ===============================
WTF_CSRF_TIME_LIMIT = 7200  # 2 hours

# ===============================
# PATH & DIRECTORIES
# ===============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime")
MEDIA_DIR = os.path.join(RUNTIME_DIR, "media")
PAYMENT_DIR = os.path.join(MEDIA_DIR, "payments")
FACES_DIR = os.path.join(MEDIA_DIR, "faces")
TEMP_DIR = os.path.join(RUNTIME_DIR, "temp_audio")
DATABASE_PATH = os.path.join(RUNTIME_DIR, "homeai.db")

# Create required directories (safe for MVP)
for d in [RUNTIME_DIR, MEDIA_DIR, PAYMENT_DIR, FACES_DIR, TEMP_DIR]:
    os.makedirs(d, exist_ok=True)

# ===============================
# EXTERNAL SERVICES
# ===============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_API_URL = (
    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    if TELEGRAM_TOKEN else None
)

# ===============================
# PLN TARIFF (Indonesia)
# ===============================
TARIF_PLN_PER_KWH = float(os.getenv("TARIF_PLN_PER_KWH", "1444.70"))

# ===============================
# FILE UPLOAD
# ===============================
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

# ===============================
# FLASK CONFIG CLASS
# ===============================
class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY must be set in environment")

    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    UPLOAD_FOLDER = MEDIA_DIR
    FACES_FOLDER = FACES_DIR
    PAYMENT_FOLDER = PAYMENT_DIR
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH


# ===============================
# HELPER FUNCTION
# ===============================
def allowed_file(filename: str) -> bool:
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )