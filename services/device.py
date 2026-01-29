# ===============================
# services/device.py - Device Service (PRODUCTION)
# ===============================
# Handles: Device CRUD, State Management, Payment Processing
# 
# IMPORTANT: Control Plane vs Edge
# - desired_state: Backend-owned intent (what user wants)
# - is_online: Edge-owned fact (actual device state)
# - This service only manages desired_state, Edge reports is_online

from typing import Optional
from datetime import datetime
from services.base import BaseService


class DeviceService(BaseService):
    """
    Service untuk operasi device/perangkat IoT.
    
    Methods required by routes:
    - get_user_devices(uid) -> routes/main.py, routes/billing.py, routes/admin.py
    - get_device(device_id, uid) -> routes/devices.py
    - request_toggle_device(device_id, uid) -> routes/devices.py
    - disable_device(device_id, uid) -> routes/devices.py
    - attach_payment_proof_bulk(device_ids, uid, filename) -> routes/billing.py
    - resubmit_payment(device_id, uid) -> routes/billing.py
    - get_device_by_id(device_id) -> routes/api.py (for edge auth)
    - payment_file_belongs_to_user(filename, uid) -> routes/media.py
    """
    
    # ===============================
    # DEVICE LISTING & RETRIEVAL
    # ===============================
    
    def get_user_devices(self, uid: int) -> list:
        """
        Get all devices for a user.
        Returns: list of device dicts with all fields.
        """
        result = self.run_query(
            """
            SELECT 
                id, user_id, name, device_type, location, power_watts,
                status, desired_state, is_online,
                payment_proof, payment_date, activated_at, activated_by,
                reject_reason, price, created_at
            FROM devices 
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (uid,)
        )
        return result or []
    
    def get_device(self, device_id: int, uid: int) -> Optional[dict]:
        """
        Get single device with OWNERSHIP CHECK.
        
        Security: Always validate user_id to prevent IDOR attacks.
        Returns: device dict or None if not found/not owned.
        """
        return self.run_query(
            """
            SELECT 
                id, user_id, name, device_type, location, power_watts,
                status, desired_state, is_online,
                payment_proof, payment_date, activated_at, activated_by,
                reject_reason, price, created_at
            FROM devices 
            WHERE id = ? AND user_id = ?
            """,
            (device_id, uid),
            one=True
        )
    
    def get_device_by_id(self, device_id: int) -> Optional[dict]:
        """
        Get device by ID only (NO ownership check).
        
        Use cases:
        - Edge/API authentication (device validates itself)
        - Admin operations
        
        WARNING: Do not use for user-facing operations!
        """
        return self.run_query(
            """
            SELECT 
                id, user_id, name, device_type, location, power_watts,
                status, desired_state, is_online,
                payment_proof, payment_date, activated_at, activated_by,
                reject_reason, price, created_at
            FROM devices 
            WHERE id = ?
            """,
            (device_id,),
            one=True
        )
    
    # ===============================
    # DEVICE CREATION
    # ===============================
    
    def add_device(
        self,
        uid: int,
        name: str,
        device_type: str = None,
        location: str = None,
        power_watts: int = 100,
        price: int = 20000
    ) -> Optional[int]:
        """
        Add new device for user.
        Initial status: 'pending_payment'
        
        Returns: device_id on success.
        """
        return self.run_query(
            """
            INSERT INTO devices 
            (user_id, name, device_type, location, power_watts, status, price)
            VALUES (?, ?, ?, ?, ?, 'pending_payment', ?)
            """,
            (uid, name.strip(), device_type, location, power_watts, price),
            commit=True
        )
    
    # ===============================
    # DEVICE STATE MANAGEMENT
    # ===============================
    
    def request_toggle_device(self, device_id: int, user_id: int) -> dict:
        """
        Request device state toggle (Control Plane intent).
        
        This sets desired_state - Edge will execute and report back.
        
        Raises: ValueError if device not found or not active
        Returns: dict with message and new desired_state
        """
        device = self.get_device(device_id, user_id)
        
        if not device:
            raise ValueError("Device tidak ditemukan")
        
        if device['status'] != 'active':
            raise ValueError(f"Device belum aktif (status: {device['status']})")
        
        # Toggle desired_state (0 -> 1, 1 -> 0)
        new_state = 0 if device['desired_state'] else 1
        state_label = "ON" if new_state else "OFF"
        
        self.run_query(
            "UPDATE devices SET desired_state = ? WHERE id = ?",
            (new_state, device_id),
            commit=True
        )
        
        return {
            "message": f"Perintah {state_label} dikirim ke device",
            "desired_state": new_state,
            "device_id": device_id
        }
    
    def disable_device(self, device_id: int, user_id: int) -> bool:
        """
        Disable/deactivate a device.
        Sets status to 'disabled' and desired_state to 0.
        
        Raises: ValueError if device not found
        Returns: True on success
        """
        device = self.get_device(device_id, user_id)
        
        if not device:
            raise ValueError("Device tidak ditemukan")
        
        result = self.run_query(
            """
            UPDATE devices 
            SET status = 'disabled', desired_state = 0 
            WHERE id = ? AND user_id = ?
            """,
            (device_id, user_id),
            commit=True
        )
        
        return result is not None and result > 0
    
    def update_device_online_status(self, device_id: int, is_online: bool) -> bool:
        """
        Update device online status (called by Edge).
        
        This is the ONLY method that should modify is_online.
        Backend should never set is_online directly.
        """
        result = self.run_query(
            "UPDATE devices SET is_online = ? WHERE id = ?",
            (1 if is_online else 0, device_id),
            commit=True
        )
        return result is not None and result > 0
    
    # ===============================
    # PAYMENT PROCESSING
    # ===============================
    
    def attach_payment_proof_bulk(
        self, 
        device_ids: list, 
        user_id: int, 
        filename: str
    ) -> int:
        """
        Attach payment proof to multiple devices.
        
        Rules:
        - Only devices with status 'pending_payment' can be updated
        - Ownership is verified for each device
        - Status changes to 'pending_review' after upload
        
        Returns: count of successfully updated devices
        """
        if not device_ids:
            return 0
        
        now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        success_count = 0
        
        for device_id in device_ids:
            try:
                device_id_int = int(device_id)
            except (ValueError, TypeError):
                continue
            
            result = self.run_query(
                """
                UPDATE devices 
                SET payment_proof = ?, 
                    payment_date = ?,
                    status = 'pending_review'
                WHERE id = ? 
                  AND user_id = ? 
                  AND status = 'pending_payment'
                """,
                (filename, now, device_id_int, user_id),
                commit=True
            )
            
            if result and result > 0:
                success_count += 1
        
        return success_count
    
    def resubmit_payment(self, device_id: int, user_id: int) -> bool:
        """
        Reset rejected device to pending_payment for resubmission.
        
        Returns: True if status was updated
        """
        result = self.run_query(
            """
            UPDATE devices 
            SET status = 'pending_payment',
                payment_proof = NULL,
                payment_date = NULL,
                reject_reason = NULL
            WHERE id = ? 
              AND user_id = ? 
              AND status = 'rejected'
            """,
            (device_id, user_id),
            commit=True
        )
        return result is not None and result > 0
    
    def payment_file_belongs_to_user(self, filename: str, user_id: int) -> bool:
        """
        Check if payment proof file belongs to user.
        Used for secure media access.
        """
        result = self.run_query(
            """
            SELECT 1 FROM devices 
            WHERE payment_proof = ? AND user_id = ?
            LIMIT 1
            """,
            (filename, user_id),
            one=True
        )
        return result is not None
    
    # ===============================
    # DEVICE LISTING BY STATUS
    # ===============================
    
    def get_devices_by_status(self, uid: int, status: str) -> list:
        """Get user's devices filtered by status."""
        result = self.run_query(
            """
            SELECT * FROM devices 
            WHERE user_id = ? AND status = ?
            ORDER BY created_at DESC
            """,
            (uid, status)
        )
        return result or []
    
    def get_pending_payment_devices(self, uid: int) -> list:
        """Get devices awaiting payment."""
        return self.get_devices_by_status(uid, 'pending_payment')
    
    def get_pending_review_devices(self, uid: int) -> list:
        """Get devices awaiting admin review."""
        return self.get_devices_by_status(uid, 'pending_review')
    
    def get_active_devices(self, uid: int) -> list:
        """Get active devices."""
        return self.get_devices_by_status(uid, 'active')
    
    def get_rejected_devices(self, uid: int) -> list:
        """Get rejected devices."""
        return self.get_devices_by_status(uid, 'rejected')
    
    # ===============================
    # DEVICE UPDATE
    # ===============================
    
    def update_device(
        self,
        device_id: int,
        user_id: int,
        name: str = None,
        device_type: str = None,
        location: str = None,
        power_watts: int = None
    ) -> bool:
        """Update device properties."""
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name.strip())
        if device_type is not None:
            updates.append("device_type = ?")
            params.append(device_type)
        if location is not None:
            updates.append("location = ?")
            params.append(location)
        if power_watts is not None:
            updates.append("power_watts = ?")
            params.append(power_watts)
        
        if not updates:
            return False
        
        params.extend([device_id, user_id])
        result = self.run_query(
            f"UPDATE devices SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
            tuple(params),
            commit=True
        )
        return result is not None and result > 0
    
    def delete_device(self, device_id: int, user_id: int) -> bool:
        """
        Delete device (hard delete).
        Consider soft delete for production.
        """
        result = self.run_query(
            "DELETE FROM devices WHERE id = ? AND user_id = ?",
            (device_id, user_id),
            commit=True
        )
        return result is not None and result > 0
