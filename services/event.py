# ===============================
# services/event.py - Event Store Service (PRODUCTION)
# ===============================
# Central event storage - ALL events pass through here
# This is the SINGLE SOURCE OF TRUTH for event history
#
# IMPORTANT:
# For EMERGENCY events, this table stores METADATA ONLY.
# Full payload is in event_evidence table.
# This prevents dual source of truth.

import json
import time
import logging
from typing import Optional, List, Dict, Any

from services.base import BaseService
from contracts.types import EventCategory, EventSeverity


# Structured logging
logger = logging.getLogger("homeai.event_service")


class EventService(BaseService):
    """
    Central Event Store Service.

    ALL events in the system MUST be stored through this service.
    This provides:
    - Idempotent event storage (duplicate event_id rejected)
    - Category-based filtering
    - Time-based queries
    - User/device scoping

    IMPORTANT - EMERGENCY EVENT HANDLING:
    For EMERGENCY events, payload contains only a REFERENCE to event_evidence table.
    This ensures single source of truth for legal evidence.

    Pattern:
    - EMERGENCY: payload = {"evidence_ref": "<event_id>", "event_type": "..."}
    - NON-EMERGENCY: payload = full event data
    """

    def store_event(
        self,
        event,  # BaseEvent
        user_id: int = None,
        device_id: int = None,
        emergency_payload_ref: str = None,
    ) -> Optional[str]:
        """
        Store an event in the event store.

        Args:
            event: BaseEvent instance (or subclass)
            user_id: Optional user context
            device_id: Optional device context
            emergency_payload_ref: For EMERGENCY events, store reference instead of payload

        Returns:
            event_id if successful, None if failed or duplicate

        IDEMPOTENCY: If event_id already exists, returns None (not an error)

        EMERGENCY HANDLING:
        If emergency_payload_ref is provided, payload becomes:
        {"evidence_ref": "<ref>", "event_type": "...", "timestamp": ...}
        This prevents storing emergency data in two places.
        """
        # Check for duplicate
        if self.exists("events", "event_id", event.event_id):
            logger.debug("Event %s already exists (idempotent)", event.event_id)
            return None  # Idempotent - already stored

        # Determine payload based on event type
        if emergency_payload_ref is not None:
            # EMERGENCY: store reference only
            payload = json.dumps({
                "evidence_ref": emergency_payload_ref,
                "event_type": event.event_type,
                "timestamp": event.timestamp,
                "_note": "Full payload in event_evidence table"
            })
            logger.info(
                "Storing EMERGENCY event metadata: %s (evidence_ref: %s)",
                event.event_id, emergency_payload_ref
            )
        else:
            # NON-EMERGENCY: store full payload
            payload = json.dumps(event.to_dict())

        result = self.run_query(
            """
            INSERT INTO events
            (event_id, event_type, category, severity, source, version, payload, created_at, user_id, device_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.event_type,
                event.category.value,
                event.severity.value,
                event.source.value,
                event.version,
                payload,
                event.timestamp,
                user_id,
                device_id,
            ),
            commit=True
        )

        if result:
            logger.debug("Event stored: %s | Type: %s | Category: %s",
                        event.event_id, event.event_type, event.category.value)
            return event.event_id
        return None

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get single event by ID."""
        event = self.run_query(
            "SELECT * FROM events WHERE event_id = ?",
            (event_id,),
            one=True
        )
        if event and event.get('payload'):
            event['payload'] = json.loads(event['payload'])
        return event

    def get_events_by_category(
        self,
        category: EventCategory,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get events filtered by category, newest first."""
        events = self.run_query(
            """
            SELECT * FROM events
            WHERE category = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (category.value, limit, offset)
        )
        for event in (events or []):
            if event.get('payload'):
                event['payload'] = json.loads(event['payload'])
        return events or []

    def get_events_by_severity(
        self,
        severity: EventSeverity,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get events filtered by severity, newest first."""
        events = self.run_query(
            """
            SELECT * FROM events
            WHERE severity = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (severity.value, limit)
        )
        for event in (events or []):
            if event.get('payload'):
                event['payload'] = json.loads(event['payload'])
        return events or []

    def get_user_events(
        self,
        user_id: int,
        category: EventCategory = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get events for a specific user."""
        if category:
            events = self.run_query(
                """
                SELECT * FROM events
                WHERE user_id = ? AND category = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, category.value, limit)
            )
        else:
            events = self.run_query(
                """
                SELECT * FROM events
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit)
            )
        for event in (events or []):
            if event.get('payload'):
                event['payload'] = json.loads(event['payload'])
        return events or []

    def get_device_events(
        self,
        device_id: int,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get events for a specific device."""
        events = self.run_query(
            """
            SELECT * FROM events
            WHERE device_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (device_id, limit)
        )
        for event in (events or []):
            if event.get('payload'):
                event['payload'] = json.loads(event['payload'])
        return events or []

    def get_recent_events(
        self,
        since_timestamp: int = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent events, optionally since a timestamp."""
        if since_timestamp:
            events = self.run_query(
                """
                SELECT * FROM events
                WHERE created_at > ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (since_timestamp, limit)
            )
        else:
            events = self.run_query(
                """
                SELECT * FROM events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,)
            )
        for event in (events or []):
            if event.get('payload'):
                event['payload'] = json.loads(event['payload'])
        return events or []

    def count_events_by_category(self) -> Dict[str, int]:
        """Get count of events by category."""
        results = self.run_query(
            """
            SELECT category, COUNT(*) as count
            FROM events
            GROUP BY category
            """
        )
        return {r['category']: r['count'] for r in (results or [])}

    def get_emergency_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Shortcut to get emergency events."""
        return self.get_events_by_category(EventCategory.EMERGENCY, limit)

    def get_anomaly_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Shortcut to get anomaly events."""
        return self.get_events_by_category(EventCategory.ANOMALY, limit)

    def get_event_with_evidence(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Get event with linked evidence (for EMERGENCY events).

        Returns combined event + evidence data.
        """
        event = self.get_event(event_id)
        if not event:
            return None

        # Check if this is an emergency with evidence reference
        if event.get('category') == 'emergency':
            payload = event.get('payload', {})
            evidence_ref = payload.get('evidence_ref') if isinstance(payload, dict) else None

            if evidence_ref:
                # Fetch evidence from event_evidence table
                evidence = self.run_query(
                    "SELECT * FROM event_evidence WHERE event_id = ?",
                    (evidence_ref,),
                    one=True
                )
                if evidence:
                    if evidence.get('payload'):
                        evidence['payload'] = json.loads(evidence['payload'])
                    event['evidence'] = evidence

        return event
