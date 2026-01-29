# ===============================
# services/user.py - User Service (PRODUCTION)
# ===============================
# Handles: Authentication, Profile, Family Members

from typing import Optional
from werkzeug.security import generate_password_hash, check_password_hash
from services.base import BaseService


class UserService(BaseService):
    """
    Service untuk operasi user & family members.
    
    Methods required by routes:
    - verify_login(email, password) -> routes/auth.py
    - email_exists(email) -> routes/auth.py
    - create_user(name, email, password) -> routes/auth.py
    - update_avatar(uid, filename) -> routes/main.py
    - get_family_members(uid) -> routes/main.py
    - add_family_member(uid, name, role, photo) -> routes/main.py
    - delete_family_member(member_id, uid) -> routes/main.py
    - family_photo_belongs_to_user(filename, uid) -> routes/media.py
    - get_by_id(uid) -> utils/session.py (optional, can use get_db directly)
    """
    
    # ===============================
    # AUTHENTICATION
    # ===============================
    
    def verify_login(self, email: str, password: str) -> Optional[dict]:
        """
        Verify user credentials.
        Returns user dict if valid, None if invalid.
        
        Security:
        - Uses werkzeug's check_password_hash
        - Excludes soft-deleted users
        """
        user = self.run_query(
            """
            SELECT id, name, email, password, role, plan_name, avatar
            FROM users 
            WHERE email = ? AND is_deleted = 0
            """,
            (email.lower().strip(),),
            one=True
        )
        
        if not user:
            return None
        
        if not check_password_hash(user['password'], password):
            return None
        
        # Return user without password hash
        return {
            'id': user['id'],
            'name': user['name'],
            'email': user['email'],
            'role': user['role'],
            'plan_name': user['plan_name'],
            'avatar': user['avatar']
        }
    
    def email_exists(self, email: str) -> bool:
        """Check if email is already registered (including soft-deleted)."""
        return self.exists("users", "email", email.lower().strip())
    
    def create_user(
        self, 
        name: str, 
        email: str, 
        password: str,
        role: str = 'user',
        plan_name: str = 'Basic'
    ) -> Optional[int]:
        """
        Create new user with hashed password.
        Returns: user_id on success, None on failure.
        """
        password_hash = generate_password_hash(password)
        
        return self.run_query(
            """
            INSERT INTO users (name, email, password, role, plan_name, verified)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (name.strip(), email.lower().strip(), password_hash, role, plan_name),
            commit=True
        )
    
    # ===============================
    # PROFILE
    # ===============================
    
    def get_by_id(self, uid: int) -> Optional[dict]:
        """
        Get user by ID.
        Used for session validation.
        """
        return self.run_query(
            """
            SELECT id, name, email, role, plan_name, avatar, verified
            FROM users 
            WHERE id = ? AND is_deleted = 0
            """,
            (uid,),
            one=True
        )
    
    def update_avatar(self, uid: int, filename: str) -> bool:
        """
        Update user's avatar filename.
        Returns: True on success.
        """
        result = self.run_query(
            "UPDATE users SET avatar = ? WHERE id = ? AND is_deleted = 0",
            (filename, uid),
            commit=True
        )
        return result is not None and result > 0
    
    def update_profile(self, uid: int, name: str = None, email: str = None) -> bool:
        """Update user profile fields."""
        updates = []
        params = []
        
        if name:
            updates.append("name = ?")
            params.append(name.strip())
        if email:
            updates.append("email = ?")
            params.append(email.lower().strip())
        
        if not updates:
            return False
        
        params.append(uid)
        result = self.run_query(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ? AND is_deleted = 0",
            tuple(params),
            commit=True
        )
        return result is not None and result > 0
    
    # ===============================
    # FAMILY MEMBERS
    # ===============================
    
    def get_family_members(self, uid: int) -> list:
        """
        Get all family members for a user.
        Returns: list of family member dicts, empty list if none.
        """
        result = self.run_query(
            """
            SELECT id, user_id, name, role, photo_identity, created_at
            FROM family_members 
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (uid,)
        )
        return result or []
    
    def add_family_member(
        self, 
        uid: int, 
        name: str, 
        role: str, 
        photo_filename: str = 'default.jpg'
    ) -> Optional[int]:
        """
        Add new family member.
        Returns: member_id on success, None on failure.
        """
        return self.run_query(
            """
            INSERT INTO family_members (user_id, name, role, photo_identity)
            VALUES (?, ?, ?, ?)
            """,
            (uid, name.strip(), role.strip() if role else '', photo_filename),
            commit=True
        )
    
    def delete_family_member(self, member_id: int, uid: int) -> bool:
        """
        Delete family member with ownership check.
        Returns: True if deleted, False if not found or not owned.
        """
        result = self.run_query(
            "DELETE FROM family_members WHERE id = ? AND user_id = ?",
            (member_id, uid),
            commit=True
        )
        return result is not None and result > 0
    
    def get_family_member(self, member_id: int, uid: int) -> Optional[dict]:
        """Get single family member with ownership check."""
        return self.run_query(
            """
            SELECT id, user_id, name, role, photo_identity, created_at
            FROM family_members 
            WHERE id = ? AND user_id = ?
            """,
            (member_id, uid),
            one=True
        )
    
    def family_photo_belongs_to_user(self, filename: str, uid: int) -> bool:
        """
        Check if a family photo belongs to user.
        Used for secure media access.
        """
        result = self.run_query(
            """
            SELECT 1 FROM family_members 
            WHERE photo_identity = ? AND user_id = ?
            LIMIT 1
            """,
            (filename, uid),
            one=True
        )
        return result is not None
    
    # ===============================
    # TELEGRAM INTEGRATION
    # ===============================
    
    def update_telegram_chat_id(self, uid: int, chat_id: str) -> bool:
        """Link user to Telegram chat."""
        result = self.run_query(
            "UPDATE users SET telegram_chat_id = ? WHERE id = ?",
            (chat_id, uid),
            commit=True
        )
        return result is not None and result > 0
    
    def get_by_telegram_chat_id(self, chat_id: str) -> Optional[dict]:
        """Find user by Telegram chat ID."""
        return self.run_query(
            """
            SELECT id, name, email, role, plan_name
            FROM users 
            WHERE telegram_chat_id = ? AND is_deleted = 0
            """,
            (chat_id,),
            one=True
        )
