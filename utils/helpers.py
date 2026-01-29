# ===============================
# utils/helpers.py - Pure Utility Functions (FINAL)
# NOTE:
# - NO DB ACCESS
# - NO FLASK CONTEXT
# - UI / DISPLAY / ESTIMATION ONLY
# ===============================

import os
import re
import uuid
import hashlib
from datetime import datetime

from config import TARIF_PLN_PER_KWH


# ===============================
# FILE UTILITIES (NON-SECURITY)
# ===============================

def get_file_extension(filename):
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[1].lower()


def generate_unique_filename(original_filename, prefix='file'):
    ext = get_file_extension(original_filename)
    timestamp = int(datetime.now().timestamp())
    unique_id = uuid.uuid4().hex[:8]
    return f"{prefix}_{timestamp}_{unique_id}.{ext}"


def get_file_size_mb(filepath):
    try:
        return os.path.getsize(filepath) / (1024 * 1024)
    except Exception:
        return 0


# ===============================
# FORMAT UTILITIES (UI ONLY)
# ===============================

def format_rupiah(amount, with_prefix=True):
    try:
        formatted = "{:,.0f}".format(float(amount)).replace(",", ".")
        return f"Rp {formatted}" if with_prefix else formatted
    except Exception:
        return "Rp 0" if with_prefix else "0"


def format_watt(watts):
    try:
        watts = float(watts)
        if watts >= 1000:
            return f"{watts/1000:.1f} kW"
        return f"{int(watts)} W"
    except Exception:
        return "0 W"


def format_datetime(dt, format_str="%d %b %Y, %H:%M"):
    try:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        return dt.strftime(format_str)
    except Exception:
        return str(dt)


def format_relative_time(dt):
    try:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))

        now = datetime.now()
        diff = now - dt
        seconds = diff.total_seconds()

        if seconds < 60:
            return "Baru saja"
        elif seconds < 3600:
            return f"{int(seconds/60)} menit lalu"
        elif seconds < 86400:
            return f"{int(seconds/3600)} jam lalu"
        elif seconds < 604800:
            return f"{int(seconds/86400)} hari lalu"
        else:
            return format_datetime(dt, "%d %b %Y")
    except Exception:
        return str(dt)


# ===============================
# ENERGY (ESTIMATION ONLY — NOT BILLING)
# ===============================

def calculate_energy_cost(watts, hours=24, days=30, tarif=None):
    """
    UI ESTIMATION ONLY.
    DO NOT use for real billing.
    """
    if tarif is None:
        tarif = TARIF_PLN_PER_KWH

    try:
        watts = float(watts)
        kwh = (watts / 1000) * hours * days
        cost = kwh * tarif
        return {
            'kwh': round(kwh, 2),
            'cost': int(cost),
            'cost_formatted': format_rupiah(cost)
        }
    except Exception:
        return {'kwh': 0, 'cost': 0, 'cost_formatted': 'Rp 0'}


def calculate_daily_kwh(watts, hours=24):
    try:
        return round((float(watts) / 1000) * hours, 3)
    except Exception:
        return 0


def watts_to_kwh(watts, hours):
    try:
        return round((float(watts) * float(hours)) / 1000, 3)
    except Exception:
        return 0


# ===============================
# STRING UTILITIES
# ===============================

def slugify(text):
    if not text:
        return ''
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug


def truncate(text, length=100, suffix='...'):
    if not text:
        return ''
    if len(text) <= length:
        return text
    return text[:length - len(suffix)].rsplit(' ', 1)[0] + suffix


def mask_email(email):
    if not email or '@' not in email:
        return email
    local, domain = email.split('@')
    masked = local[:2] + '***' if len(local) > 2 else local + '***'
    return f"{masked}@{domain}"


# ===============================
# SECURITY HELPERS (NON-AUTH)
# ===============================

def generate_random_id(length=8):
    return uuid.uuid4().hex[:length]


def hash_string(text):
    """
    NOT FOR PASSWORD.
    Use only for checksum / identifier.
    """
    return hashlib.sha256(text.encode()).hexdigest()


def generate_token(length=32):
    return uuid.uuid4().hex[:length]


# ===============================
# VALIDATION UTILITIES
# ===============================

def is_valid_email(email):
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def is_valid_phone(phone):
    if not phone:
        return False
    phone = re.sub(r'[\s-]', '', phone)
    pattern = r'^(\+62|62|0)8[1-9][0-9]{7,10}$'
    return bool(re.match(pattern, phone))


def sanitize_input(text):
    if not text:
        return ''
    return re.sub(r'[<>"\';\\]', '', str(text)).strip()