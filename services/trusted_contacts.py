# ===============================
# services/trusted_contacts.py - Trusted Contacts Service (PRODUCTION)
# ===============================
# Manages trusted contacts for emergency notifications.
#
# PHILOSOPHY:
# - Violence detection: NEVER stay silent, alert trusted humans
# - User maintains control over who gets alerted
# - Priority system ensures most important contacts are reached first
# - Verification required before contacts can receive alerts

import time
import logging
from typing import Optional, List, Dict, Any

from services.base import BaseService


logger = logging.getLogger("homeai.trusted_contacts")


class TrustedContactsService(BaseService):
    """
    Trusted Contacts Management Service.

    Trusted contacts are people the user designates to receive alerts
    during emergencies. This is NOT the same as family members.

    IMPORTANT DISTINCTIONS:
    - Family members: People who live in the house, can control devices
    - Trusted contacts: External people who receive emergency alerts

    A family member CAN also be a trusted contact, but they're separate concepts.

    NOTIFICATION PRIORITY:
    - Priority 1: First to be notified (spouse, parent, etc.)
    - Priority 2: Secondary (sibling, close friend)
    - Priority 3+: Tertiary contacts

    NOTIFICATION TYPES:
    - Intrusion: Unknown person detected
    - Fire: Smoke/fire detected
    - Violence: Domestic violence indicators
    - Emergency: Panic button, general emergency

    VERIFICATION:
    - Contacts should be verified before they can receive alerts
    - Verification ensures the phone/email is valid and belongs to intended person
    """

    def add_contact(
        self,
        user_id: int,
        name: str,
        relationship: str,
        phone: str = None,
        email: str = None,
        telegram_chat_id: str = None,
        priority: int = 1,
        notify_intrusion: bool = True,
        notify_fire: bool = True,
        notify_violence: bool = True,
        notify_emergency: bool = True,
    ) -> Optional[int]:
        """
        Add a trusted contact.

        Args:
            user_id: Owner of this contact
            name: Contact's name
            relationship: How they relate to user (spouse, parent, friend, etc.)
            phone: Phone number for SMS/call
            email: Email for notifications
            telegram_chat_id: Telegram for instant messaging
            priority: Notification priority (lower = higher priority)
            notify_*: Which events to notify for

        Returns:
            Contact ID if successful, None if failed

        Raises:
            ValueError: If no contact method provided
        """
        if not phone and not email and not telegram_chat_id:
            raise ValueError("At least one contact method (phone, email, telegram) required")

        now = int(time.time())

        result = self.run_query(
            """
            INSERT INTO trusted_contacts (
                user_id, name, relationship, phone, email, telegram_chat_id,
                priority, notify_intrusion, notify_fire, notify_violence,
                notify_emergency, is_active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                user_id, name, relationship, phone, email, telegram_chat_id,
                priority, notify_intrusion, notify_fire, notify_violence,
                notify_emergency, now
            ),
            commit=True
        )

        if result:
            logger.info(
                "Trusted contact added: user %d | name: %s | relationship: %s",
                user_id, name, relationship
            )
            return result

        return None

    def update_contact(
        self,
        contact_id: int,
        user_id: int,
        **updates
    ) -> bool:
        """
        Update a trusted contact.

        Only the owner (user_id) can update their contacts.

        Args:
            contact_id: ID of contact to update
            user_id: Must match owner
            **updates: Fields to update

        Returns:
            True if updated, False if not found or not authorized
        """
        # Verify ownership
        contact = self.run_query(
            "SELECT user_id FROM trusted_contacts WHERE id = ?",
            (contact_id,),
            one=True
        )

        if not contact or contact["user_id"] != user_id:
            logger.warning(
                "Unauthorized contact update attempt: contact %d by user %d",
                contact_id, user_id
            )
            return False

        # Build update query
        allowed_fields = [
            "name", "relationship", "phone", "email", "telegram_chat_id",
            "priority", "notify_intrusion", "notify_fire", "notify_violence",
            "notify_emergency", "is_active"
        ]

        updates_filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not updates_filtered:
            return False

        updates_filtered["updated_at"] = int(time.time())

        set_clause = ", ".join(f"{k} = ?" for k in updates_filtered.keys())
        values = list(updates_filtered.values()) + [contact_id]

        result = self.run_query(
            f"UPDATE trusted_contacts SET {set_clause} WHERE id = ?",
            values,
            commit=True
        )

        if result:
            logger.info("Trusted contact updated: %d", contact_id)
            return True

        return False

    def remove_contact(self, contact_id: int, user_id: int) -> bool:
        """
        Remove a trusted contact.

        Note: This is a soft delete (is_active = 0) for audit trail.

        Args:
            contact_id: ID of contact to remove
            user_id: Must match owner

        Returns:
            True if removed, False if not found or not authorized
        """
        now = int(time.time())

        result = self.run_query(
            """
            UPDATE trusted_contacts
            SET is_active = 0, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (now, contact_id, user_id),
            commit=True
        )

        if result and result > 0:
            logger.info("Trusted contact removed: %d by user %d", contact_id, user_id)
            return True

        return False

    def get_contact(self, contact_id: int, user_id: int = None) -> Optional[Dict[str, Any]]:
        """Get single contact, optionally verifying ownership."""
        if user_id:
            return self.run_query(
                "SELECT * FROM trusted_contacts WHERE id = ? AND user_id = ?",
                (contact_id, user_id),
                one=True
            )
        return self.run_query(
            "SELECT * FROM trusted_contacts WHERE id = ?",
            (contact_id,),
            one=True
        )

    def get_user_contacts(
        self,
        user_id: int,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """Get all contacts for a user, ordered by priority."""
        if active_only:
            return self.run_query(
                """
                SELECT * FROM trusted_contacts
                WHERE user_id = ? AND is_active = 1
                ORDER BY priority ASC, created_at ASC
                """,
                (user_id,)
            ) or []
        return self.run_query(
            """
            SELECT * FROM trusted_contacts
            WHERE user_id = ?
            ORDER BY priority ASC, created_at ASC
            """,
            (user_id,)
        ) or []

    def get_contacts_for_event(
        self,
        user_id: int,
        event_type: str
    ) -> List[Dict[str, Any]]:
        """
        Get contacts that should be notified for a specific event type.

        Args:
            user_id: Owner of contacts
            event_type: One of 'intrusion', 'fire', 'violence', 'emergency'

        Returns:
            List of contacts to notify, ordered by priority
        """
        # Map event type to column
        column_map = {
            "intrusion": "notify_intrusion",
            "fire": "notify_fire",
            "violence": "notify_violence",
            "emergency": "notify_emergency",
            "water_leak": "notify_emergency",
            "power_emergency": "notify_emergency",
            "panic": "notify_emergency",
        }

        column = column_map.get(event_type, "notify_emergency")

        return self.run_query(
            f"""
            SELECT * FROM trusted_contacts
            WHERE user_id = ? AND is_active = 1 AND {column} = 1
            ORDER BY priority ASC, created_at ASC
            """,
            (user_id,)
        ) or []

    def verify_contact(self, contact_id: int, user_id: int) -> bool:
        """
        Mark a contact as verified.

        Verification should happen after confirming the contact method works
        (e.g., user confirmed they received test notification).

        Args:
            contact_id: Contact to verify
            user_id: Must match owner

        Returns:
            True if verified, False if not found or not authorized
        """
        now = int(time.time())

        result = self.run_query(
            """
            UPDATE trusted_contacts
            SET verified_at = ?, updated_at = ?
            WHERE id = ? AND user_id = ? AND is_active = 1
            """,
            (now, now, contact_id, user_id),
            commit=True
        )

        if result and result > 0:
            logger.info("Trusted contact verified: %d", contact_id)
            return True

        return False

    def get_verified_contacts_for_event(
        self,
        user_id: int,
        event_type: str
    ) -> List[Dict[str, Any]]:
        """
        Get only verified contacts for an event.

        For critical alerts (violence, fire), we may still want to notify
        unverified contacts, but this method returns only verified ones
        for situations where we need confirmed delivery.
        """
        column_map = {
            "intrusion": "notify_intrusion",
            "fire": "notify_fire",
            "violence": "notify_violence",
            "emergency": "notify_emergency",
        }

        column = column_map.get(event_type, "notify_emergency")

        return self.run_query(
            f"""
            SELECT * FROM trusted_contacts
            WHERE user_id = ? AND is_active = 1 AND verified_at IS NOT NULL AND {column} = 1
            ORDER BY priority ASC, created_at ASC
            """,
            (user_id,)
        ) or []

    def set_notification_preferences(
        self,
        contact_id: int,
        user_id: int,
        notify_intrusion: bool = None,
        notify_fire: bool = None,
        notify_violence: bool = None,
        notify_emergency: bool = None,
    ) -> bool:
        """
        Update notification preferences for a contact.

        Args:
            contact_id: Contact to update
            user_id: Must match owner
            notify_*: Which events to notify for (None = don't change)

        Returns:
            True if updated
        """
        updates = {}
        if notify_intrusion is not None:
            updates["notify_intrusion"] = notify_intrusion
        if notify_fire is not None:
            updates["notify_fire"] = notify_fire
        if notify_violence is not None:
            updates["notify_violence"] = notify_violence
        if notify_emergency is not None:
            updates["notify_emergency"] = notify_emergency

        if not updates:
            return False

        return self.update_contact(contact_id, user_id, **updates)

    def get_contact_count(self, user_id: int) -> Dict[str, int]:
        """Get contact statistics for a user."""
        result = self.run_query(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN verified_at IS NOT NULL THEN 1 ELSE 0 END) as verified
            FROM trusted_contacts
            WHERE user_id = ?
            """,
            (user_id,),
            one=True
        )

        if result:
            return {
                "total": result["total"] or 0,
                "active": result["active"] or 0,
                "verified": result["verified"] or 0,
            }

        return {"total": 0, "active": 0, "verified": 0}

    def has_verified_contacts(self, user_id: int) -> bool:
        """Check if user has at least one verified contact."""
        result = self.run_query(
            """
            SELECT COUNT(*) as c FROM trusted_contacts
            WHERE user_id = ? AND is_active = 1 AND verified_at IS NOT NULL
            """,
            (user_id,),
            one=True
        )
        return result and result["c"] > 0
