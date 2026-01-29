# ===============================
# services/admin.py - Admin Service (PRODUCTION)
# ===============================
# Handles: Admin dashboard, user management, device approval/rejection
#
# NOTE: This service uses get_db() directly for compatibility with
# existing code. It can be migrated to BaseService pattern if needed.

from datetime import datetime
from typing import Optional
from services.base import BaseService


class AdminService(BaseService):
    """
    Service untuk operasi admin panel.
    
    Methods required by routes:
    - get_dashboard_data() -> routes/admin.py
    - get_user_detail(uid) -> routes/admin.py
    - get_all_orders() -> routes/admin.py
    - activate_device(device_id, admin_id) -> routes/admin.py
    - reject_device(device_id, reason, admin_id) -> routes/admin.py
    - delete_user(uid, admin_id) -> routes/admin.py
    - update_user_plan(uid, plan, admin_id) -> routes/admin.py
    """
    
    # ===============================
    # DASHBOARD
    # ===============================
    
    def get_dashboard_data(self) -> dict:
        """
        Get all data for admin dashboard.
        Returns: dict with users list and stats.
        """
        users = self.run_query(
            """
            SELECT id, name, email, role, plan_name, avatar, verified, created_at
            FROM users 
            WHERE is_deleted = 0
            ORDER BY created_at DESC
            """
        ) or []
        
        stats = self.run_query(
            """
            SELECT
                (SELECT COUNT(*) FROM users WHERE is_deleted = 0) AS total_users,
                (SELECT COUNT(*) FROM devices) AS total_devices,
                (SELECT COUNT(*) FROM devices WHERE status = 'pending_review') AS pending_review,
                (SELECT COUNT(*) FROM devices WHERE status = 'active') AS active_devices
            """,
            one=True
        ) or {}
        
        return {
            "users": users,
            "stats": {
                "total_users": stats.get("total_users", 0),
                "total_devices": stats.get("total_devices", 0),
                "pending_review": stats.get("pending_review", 0),
                "active_devices": stats.get("active_devices", 0),
            }
        }
    
    # ===============================
    # USER MANAGEMENT
    # ===============================
    
    def get_user_detail(self, uid: int) -> Optional[dict]:
        """Get user details for admin view."""
        return self.run_query(
            """
            SELECT id, name, email, role, plan_name, avatar, verified,
                   telegram_chat_id, created_at
            FROM users 
            WHERE id = ? AND is_deleted = 0
            """,
            (uid,),
            one=True
        )
    
    def delete_user(self, uid: int, admin_id: int) -> bool:
        """
        Soft-delete user (set is_deleted = 1).
        Logs action for audit trail.
        """
        result = self.run_query(
            "UPDATE users SET is_deleted = 1 WHERE id = ?",
            (uid,),
            commit=True
        )
        
        if result:
            self._log_action(admin_id, "delete_user", uid)
        
        return result is not None and result > 0
    
    def restore_user(self, uid: int, admin_id: int) -> bool:
        """Restore soft-deleted user."""
        result = self.run_query(
            "UPDATE users SET is_deleted = 0 WHERE id = ?",
            (uid,),
            commit=True
        )
        
        if result:
            self._log_action(admin_id, "restore_user", uid)
        
        return result is not None and result > 0
    
    def update_user_plan(self, uid: int, plan: str, admin_id: int) -> bool:
        """Update user's subscription plan."""
        result = self.run_query(
            "UPDATE users SET plan_name = ? WHERE id = ? AND is_deleted = 0",
            (plan, uid),
            commit=True
        )
        
        if result:
            self._log_action(admin_id, f"update_plan:{plan}", uid)
        
        return result is not None and result > 0
    
    def update_user_role(self, uid: int, role: str, admin_id: int) -> bool:
        """Update user's role (user/admin)."""
        if role not in ('user', 'admin'):
            return False
        
        result = self.run_query(
            "UPDATE users SET role = ? WHERE id = ? AND is_deleted = 0",
            (role, uid),
            commit=True
        )
        
        if result:
            self._log_action(admin_id, f"update_role:{role}", uid)
        
        return result is not None and result > 0
    
    # ===============================
    # DEVICE ORDER MANAGEMENT
    # ===============================
    
    def get_all_orders(self) -> list:
        """
        Get all device orders with user info.
        Ordered by priority: pending_review first, then by date.
        """
        result = self.run_query(
            """
            SELECT
                d.id, d.name, d.device_type, d.status, d.created_at,
                d.payment_proof, d.payment_date, d.reject_reason, d.price,
                d.activated_at, d.activated_by,
                u.id AS user_id, u.name AS user_name, u.email AS user_email
            FROM devices d
            LEFT JOIN users u ON d.user_id = u.id
            ORDER BY
                CASE d.status
                    WHEN 'pending_review' THEN 1
                    WHEN 'pending_payment' THEN 2
                    WHEN 'active' THEN 3
                    WHEN 'rejected' THEN 4
                    ELSE 5
                END,
                d.created_at DESC
            """
        )
        return result or []
    
    def get_pending_orders(self) -> list:
        """Get only pending_review orders."""
        result = self.run_query(
            """
            SELECT
                d.id, d.name, d.device_type, d.status, d.created_at,
                d.payment_proof, d.payment_date, d.price,
                u.id AS user_id, u.name AS user_name, u.email AS user_email
            FROM devices d
            LEFT JOIN users u ON d.user_id = u.id
            WHERE d.status = 'pending_review'
            ORDER BY d.payment_date ASC
            """
        )
        return result or []
    
    def activate_device(self, device_id: int, admin_id: int) -> bool:
        """
        Activate a device after payment verification.
        Only works for devices with status 'pending_review'.
        """
        now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        result = self.run_query(
            """
            UPDATE devices
            SET status = 'active',
                activated_at = ?,
                activated_by = ?
            WHERE id = ? AND status = 'pending_review'
            """,
            (now, admin_id, device_id),
            commit=True
        )
        
        if result and result > 0:
            self._log_action(admin_id, "activate_device", device_id)
            return True
        
        return False
    
    def reject_device(
        self, 
        device_id: int, 
        reason: str, 
        admin_id: int
    ) -> bool:
        """
        Reject a device payment.
        Only works for devices with status 'pending_review'.
        """
        result = self.run_query(
            """
            UPDATE devices
            SET status = 'rejected',
                reject_reason = ?
            WHERE id = ? AND status = 'pending_review'
            """,
            (reason, device_id),
            commit=True
        )
        
        if result and result > 0:
            self._log_action(admin_id, "reject_device", device_id)
            return True
        
        return False
    
    # ===============================
    # AUDIT LOGGING
    # ===============================
    
    def _log_action(self, admin_id: int, action: str, target_id: int) -> None:
        """Log admin action for audit trail."""
        now_ts = int(datetime.utcnow().timestamp())
        
        self.run_query(
            """
            INSERT INTO admin_logs (admin_id, action, target_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (admin_id, action, target_id, now_ts),
            commit=True
        )
    
    def get_admin_logs(self, limit: int = 100) -> list:
        """Get recent admin activity logs."""
        result = self.run_query(
            """
            SELECT 
                al.id, al.action, al.target_id, al.created_at,
                u.name AS admin_name
            FROM admin_logs al
            LEFT JOIN users u ON al.admin_id = u.id
            ORDER BY al.created_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        return result or []
    
    def get_admin_logs_by_admin(self, admin_id: int, limit: int = 50) -> list:
        """Get activity logs for specific admin."""
        result = self.run_query(
            """
            SELECT id, action, target_id, created_at
            FROM admin_logs
            WHERE admin_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (admin_id, limit)
        )
        return result or []
    
    # ===============================
    # STATISTICS
    # ===============================
    
    def get_revenue_stats(self) -> dict:
        """Get revenue statistics from activated devices."""
        result = self.run_query(
            """
            SELECT
                COUNT(*) as total_activated,
                SUM(price) as total_revenue,
                AVG(price) as avg_price
            FROM devices
            WHERE status = 'active'
            """,
            one=True
        )
        
        return {
            "total_activated": result.get("total_activated", 0) if result else 0,
            "total_revenue": result.get("total_revenue", 0) if result else 0,
            "avg_price": round(result.get("avg_price", 0) or 0, 2) if result else 0,
        }
    
    def get_user_stats(self) -> dict:
        """Get user registration statistics."""
        result = self.run_query(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN role = 'admin' THEN 1 ELSE 0 END) as admins,
                SUM(CASE WHEN telegram_chat_id IS NOT NULL THEN 1 ELSE 0 END) as telegram_linked
            FROM users
            WHERE is_deleted = 0
            """,
            one=True
        )
        
        return {
            "total_users": result.get("total", 0) if result else 0,
            "admin_count": result.get("admins", 0) if result else 0,
            "telegram_linked": result.get("telegram_linked", 0) if result else 0,
        }
