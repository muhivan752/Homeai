# ===============================
# services/confirmation.py - Confirmation Flow Service (PRODUCTION)
# ===============================
# Handles the 30-second confirmation window for emergency events.
#
# CRITICAL PHILOSOPHY:
# - 30 seconds is NON-NEGOTIABLE minimum
# - User ALWAYS gets chance to confirm/deny before escalation
# - Expired confirmations trigger policy-defined fallback action
# - All decisions are logged for audit

import time
import logging
import threading
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

from services.base import BaseService
from contracts.types import (
    ConfirmationStatus,
    DEFAULT_CONFIRMATION_WINDOW,
)


logger = logging.getLogger("homeai.confirmation")


@dataclass
class ConfirmationRequest:
    """Represents a pending confirmation request."""
    id: int
    user_id: int
    event_id: str
    event_type: str
    expires_at: int
    fallback_action: str
    status: ConfirmationStatus
    created_at: int


class ConfirmationService(BaseService):
    """
    Confirmation Flow Service.

    Manages the 30-second confirmation window for emergency events.

    FLOW:
    1. Emergency event detected
    2. Create confirmation request with 30-second window
    3. Notify user immediately
    4. Wait for user response OR timeout
    5. If confirmed_safe: cancel escalation
    6. If confirmed_threat: immediate full escalation
    7. If expired: execute fallback action

    GUARANTEES:
    - Minimum 30-second window (enforced at code level)
    - User notification is ALWAYS attempted
    - Timeout handling is automatic via background worker
    - All state changes are logged

    ARCHITECTURE:
    - Watchdog thread checks for expired confirmations every 5 seconds
    - Callbacks are registered for each confirmation type
    - State machine ensures valid transitions only
    """

    def __init__(self, db_path: str):
        super().__init__(db_path)
        self._callbacks: Dict[str, Callable] = {}
        self._watchdog_running = False
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_interval = 5  # Check every 5 seconds
        self._shutdown_event = threading.Event()

    def start_watchdog(self):
        """Start the confirmation watchdog thread."""
        if self._watchdog_running:
            return

        self._watchdog_running = True
        self._shutdown_event.clear()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_worker,
            name="confirmation_watchdog",
            daemon=True
        )
        self._watchdog_thread.start()
        logger.info("Confirmation watchdog started")

    def stop_watchdog(self):
        """Stop the confirmation watchdog thread."""
        self._watchdog_running = False
        self._shutdown_event.set()
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=10)
        logger.info("Confirmation watchdog stopped")

    def _watchdog_worker(self):
        """Background worker that checks for expired confirmations."""
        logger.info("Confirmation watchdog worker started")

        while not self._shutdown_event.is_set():
            try:
                self._process_expired_confirmations()
            except Exception as e:
                logger.error("Watchdog error: %s", e)

            # Wait for interval or shutdown
            self._shutdown_event.wait(timeout=self._watchdog_interval)

        logger.info("Confirmation watchdog worker stopped")

    def _process_expired_confirmations(self):
        """Find and process expired confirmations."""
        now = int(time.time())

        expired = self.run_query(
            """
            SELECT * FROM pending_confirmations
            WHERE status = 'pending' AND expires_at <= ?
            """,
            (now,)
        )

        if not expired:
            return

        for confirmation in expired:
            try:
                self._handle_expiration(confirmation)
            except Exception as e:
                logger.error(
                    "Failed to handle expiration for %s: %s",
                    confirmation["event_id"], e
                )

    def _handle_expiration(self, confirmation: Dict[str, Any]):
        """Handle a single expired confirmation."""
        now = int(time.time())

        # Update status to expired
        self.run_query(
            """
            UPDATE pending_confirmations
            SET status = 'expired', escalated = 1, escalated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now, confirmation["id"]),
            commit=True
        )

        logger.warning(
            "Confirmation expired: event %s | user %d | fallback: %s",
            confirmation["event_id"],
            confirmation["user_id"],
            confirmation["fallback_action"]
        )

        # Execute callback if registered
        callback_key = f"expired_{confirmation['event_type']}"
        if callback_key in self._callbacks:
            try:
                self._callbacks[callback_key](confirmation)
            except Exception as e:
                logger.error("Expiration callback failed: %s", e)

        # Also try generic expiration callback
        if "on_expired" in self._callbacks:
            try:
                self._callbacks["on_expired"](confirmation)
            except Exception as e:
                logger.error("Generic expiration callback failed: %s", e)

    def register_callback(self, event: str, callback: Callable):
        """
        Register callback for confirmation events.

        Events:
        - "on_expired": Called when any confirmation expires
        - "expired_{event_type}": Called when specific type expires
        - "on_confirmed_safe": Called when user confirms safe
        - "on_confirmed_threat": Called when user confirms threat

        Args:
            event: Event name
            callback: Function to call with confirmation dict
        """
        self._callbacks[event] = callback
        logger.debug("Callback registered: %s", event)

    def create_confirmation(
        self,
        user_id: int,
        event_id: str,
        event_type: str,
        fallback_action: str,
        window_seconds: int = DEFAULT_CONFIRMATION_WINDOW,
    ) -> Optional[int]:
        """
        Create a new confirmation request.

        Args:
            user_id: User who needs to confirm
            event_id: Event that triggered this
            event_type: Type of event (intrusion, fire, etc.)
            fallback_action: What to do if no response
            window_seconds: How long to wait (minimum 30 seconds)

        Returns:
            Confirmation ID if created, None if failed

        CRITICAL: window_seconds is enforced to minimum 30 seconds
        """
        # ENFORCE MINIMUM WINDOW
        if window_seconds < DEFAULT_CONFIRMATION_WINDOW:
            logger.warning(
                "Attempted to create confirmation with %ds window, enforcing %ds",
                window_seconds, DEFAULT_CONFIRMATION_WINDOW
            )
            window_seconds = DEFAULT_CONFIRMATION_WINDOW

        now = int(time.time())
        expires_at = now + window_seconds

        result = self.run_query(
            """
            INSERT INTO pending_confirmations (
                user_id, event_id, event_type,
                created_at, expires_at, fallback_action, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """,
            (user_id, event_id, event_type, now, expires_at, fallback_action),
            commit=True
        )

        if result:
            logger.info(
                "Confirmation created: event %s | user %d | expires in %ds",
                event_id, user_id, window_seconds
            )
            return result

        return None

    def confirm_safe(
        self,
        confirmation_id: int = None,
        event_id: str = None,
        user_id: int = None,
        response_method: str = "app"
    ) -> bool:
        """
        User confirms situation is SAFE (false alarm).

        Cancels any pending escalation.

        Args:
            confirmation_id: ID of confirmation (or use event_id)
            event_id: Event ID to confirm (if confirmation_id not provided)
            user_id: Must match owner for security
            response_method: How user responded (app, telegram, voice, etc.)

        Returns:
            True if confirmed, False if not found or already processed
        """
        now = int(time.time())

        # Find the confirmation
        if confirmation_id:
            confirmation = self.run_query(
                "SELECT * FROM pending_confirmations WHERE id = ?",
                (confirmation_id,),
                one=True
            )
        elif event_id and user_id:
            confirmation = self.run_query(
                """
                SELECT * FROM pending_confirmations
                WHERE event_id = ? AND user_id = ? AND status = 'pending'
                """,
                (event_id, user_id),
                one=True
            )
        else:
            return False

        if not confirmation:
            return False

        # Verify ownership
        if user_id and confirmation["user_id"] != user_id:
            logger.warning(
                "Unauthorized confirmation attempt: %d by user %d",
                confirmation["id"], user_id
            )
            return False

        # Check if still pending
        if confirmation["status"] != "pending":
            logger.info(
                "Confirmation already processed: %d | status: %s",
                confirmation["id"], confirmation["status"]
            )
            return False

        # Update status
        result = self.run_query(
            """
            UPDATE pending_confirmations
            SET status = 'confirmed_safe', responded_at = ?, response_method = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now, response_method, confirmation["id"]),
            commit=True
        )

        if result:
            logger.info(
                "Confirmed SAFE: event %s | user %d | method: %s",
                confirmation["event_id"], confirmation["user_id"], response_method
            )

            # Execute callback
            if "on_confirmed_safe" in self._callbacks:
                try:
                    self._callbacks["on_confirmed_safe"](confirmation)
                except Exception as e:
                    logger.error("Safe confirmation callback failed: %s", e)

            return True

        return False

    def confirm_threat(
        self,
        confirmation_id: int = None,
        event_id: str = None,
        user_id: int = None,
        response_method: str = "app"
    ) -> bool:
        """
        User confirms situation is a REAL THREAT.

        Triggers immediate full escalation.

        Args:
            confirmation_id: ID of confirmation (or use event_id)
            event_id: Event ID to confirm (if confirmation_id not provided)
            user_id: Must match owner for security
            response_method: How user responded

        Returns:
            True if confirmed, False if not found or already processed
        """
        now = int(time.time())

        # Find the confirmation
        if confirmation_id:
            confirmation = self.run_query(
                "SELECT * FROM pending_confirmations WHERE id = ?",
                (confirmation_id,),
                one=True
            )
        elif event_id and user_id:
            confirmation = self.run_query(
                """
                SELECT * FROM pending_confirmations
                WHERE event_id = ? AND user_id = ? AND status = 'pending'
                """,
                (event_id, user_id),
                one=True
            )
        else:
            return False

        if not confirmation:
            return False

        # Verify ownership
        if user_id and confirmation["user_id"] != user_id:
            logger.warning(
                "Unauthorized confirmation attempt: %d by user %d",
                confirmation["id"], user_id
            )
            return False

        # Check if still pending
        if confirmation["status"] != "pending":
            logger.info(
                "Confirmation already processed: %d | status: %s",
                confirmation["id"], confirmation["status"]
            )
            return False

        # Update status with escalation
        result = self.run_query(
            """
            UPDATE pending_confirmations
            SET status = 'confirmed_threat', responded_at = ?,
                response_method = ?, escalated = 1, escalated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now, response_method, now, confirmation["id"]),
            commit=True
        )

        if result:
            logger.warning(
                "Confirmed THREAT: event %s | user %d | ESCALATING",
                confirmation["event_id"], confirmation["user_id"]
            )

            # Execute callback
            if "on_confirmed_threat" in self._callbacks:
                try:
                    self._callbacks["on_confirmed_threat"](confirmation)
                except Exception as e:
                    logger.error("Threat confirmation callback failed: %s", e)

            return True

        return False

    def cancel_confirmation(
        self,
        confirmation_id: int = None,
        event_id: str = None,
        reason: str = "system_cancelled"
    ) -> bool:
        """
        Cancel a pending confirmation.

        Used when the triggering event is invalidated or superseded.

        Args:
            confirmation_id: ID of confirmation (or use event_id)
            event_id: Event ID to cancel
            reason: Why it was cancelled

        Returns:
            True if cancelled
        """
        now = int(time.time())

        if confirmation_id:
            result = self.run_query(
                """
                UPDATE pending_confirmations
                SET status = 'cancelled', responded_at = ?, response_method = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now, reason, confirmation_id),
                commit=True
            )
        elif event_id:
            result = self.run_query(
                """
                UPDATE pending_confirmations
                SET status = 'cancelled', responded_at = ?, response_method = ?
                WHERE event_id = ? AND status = 'pending'
                """,
                (now, reason, event_id),
                commit=True
            )
        else:
            return False

        if result:
            logger.info("Confirmation cancelled: %s", event_id or confirmation_id)
            return True

        return False

    def get_pending(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all pending confirmations for a user."""
        return self.run_query(
            """
            SELECT * FROM pending_confirmations
            WHERE user_id = ? AND status = 'pending'
            ORDER BY expires_at ASC
            """,
            (user_id,)
        ) or []

    def get_pending_for_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get pending confirmation for a specific event."""
        return self.run_query(
            """
            SELECT * FROM pending_confirmations
            WHERE event_id = ? AND status = 'pending'
            """,
            (event_id,),
            one=True
        )

    def get_confirmation_history(
        self,
        user_id: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get confirmation history for a user."""
        return self.run_query(
            """
            SELECT * FROM pending_confirmations
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit)
        ) or []

    def get_time_remaining(self, confirmation_id: int) -> Optional[int]:
        """
        Get seconds remaining before confirmation expires.

        Returns:
            Seconds remaining (can be negative if expired), None if not found
        """
        confirmation = self.run_query(
            "SELECT expires_at FROM pending_confirmations WHERE id = ?",
            (confirmation_id,),
            one=True
        )

        if confirmation:
            return confirmation["expires_at"] - int(time.time())

        return None

    def extend_window(
        self,
        confirmation_id: int,
        additional_seconds: int,
        max_total_seconds: int = 300  # Max 5 minutes total
    ) -> bool:
        """
        Extend confirmation window.

        Can be used when user is actively engaging but needs more time.
        Has hard cap to prevent indefinite postponement.

        Args:
            confirmation_id: Confirmation to extend
            additional_seconds: How much more time
            max_total_seconds: Maximum total window (default 5 min)

        Returns:
            True if extended
        """
        confirmation = self.run_query(
            "SELECT * FROM pending_confirmations WHERE id = ? AND status = 'pending'",
            (confirmation_id,),
            one=True
        )

        if not confirmation:
            return False

        # Calculate new expiry
        now = int(time.time())
        new_expires = confirmation["expires_at"] + additional_seconds

        # Check max limit
        total_window = new_expires - confirmation["created_at"]
        if total_window > max_total_seconds:
            new_expires = confirmation["created_at"] + max_total_seconds
            logger.warning(
                "Extension capped at max window: %ds",
                max_total_seconds
            )

        # Don't allow extending past current time (already expired)
        if new_expires <= now:
            return False

        result = self.run_query(
            """
            UPDATE pending_confirmations
            SET expires_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (new_expires, confirmation_id),
            commit=True
        )

        if result:
            logger.info(
                "Confirmation extended: %d | new expiry: %d",
                confirmation_id, new_expires
            )
            return True

        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get confirmation statistics."""
        total = self.run_query(
            "SELECT COUNT(*) as c FROM pending_confirmations",
            one=True
        )

        by_status = self.run_query(
            """
            SELECT status, COUNT(*) as count
            FROM pending_confirmations
            GROUP BY status
            """
        )

        avg_response_time = self.run_query(
            """
            SELECT AVG(responded_at - created_at) as avg_time
            FROM pending_confirmations
            WHERE responded_at IS NOT NULL
            """,
            one=True
        )

        escalated = self.run_query(
            "SELECT COUNT(*) as c FROM pending_confirmations WHERE escalated = 1",
            one=True
        )

        return {
            "total": total["c"] if total else 0,
            "by_status": {r["status"]: r["count"] for r in (by_status or [])},
            "avg_response_time_seconds": avg_response_time["avg_time"] if avg_response_time else None,
            "total_escalated": escalated["c"] if escalated else 0,
        }
