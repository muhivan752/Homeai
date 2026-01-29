# ===============================
# utils/session.py - Session & User State Management (FINAL)
# ===============================

from flask import session, g, current_app
from database import get_db


def get_current_user():
    """
    Get current logged-in user from session.
    Uses DB lookup with soft-delete guard.
    """
    uid = session.get("user_id")
    if not uid:
        return None

    try:
        db = get_db()
        cur = db.execute(
            """
            SELECT id, name, email, role, plan_name, avatar
            FROM users
            WHERE id=? AND is_deleted=0
            """,
            (uid,)
        )
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        current_app.logger.exception("Failed to load current user from session")
        return None


def set_user_session(user: dict):
    """Set user session after successful login"""
    session.permanent = True
    session['user_id'] = user['id']
    session['role'] = user.get('role', 'user')
    session['user_name'] = user.get('name', '')


def clear_session():
    """Clear all session data (logout)"""
    session.clear()


def is_authenticated() -> bool:
    """Check if user is logged in"""
    return bool(session.get('user_id'))


def get_user_id():
    """Get current user ID from session"""
    return session.get('user_id')


def get_user_role():
    """Get current user role from session"""
    return session.get('role')


def is_admin() -> bool:
    """Check if current user is admin"""
    return get_user_role() == 'admin'


def update_session_user(user: dict):
    """Update session with fresh user data"""
    if not user:
        return
    session['role'] = user.get('role', 'user')
    session['user_name'] = user.get('name', '')


def get_session_data():
    """
    Debug helper (DO NOT expose publicly)
    """
    return {
        'user_id': session.get('user_id'),
        'role': session.get('role'),
        'user_name': session.get('user_name'),
        'is_authenticated': is_authenticated(),
        'is_admin': is_admin(),
    }