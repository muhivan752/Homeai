# ===============================
# services/event.py - Event Store Service (PRODUCTION)
# ===============================
# Central event storage - ALL events pass through here
# This is the SINGLE SOURCE OF TRUTH for event history

import json
import time
from typing import Optional, List, Dict, Any

from services.base import BaseService
from contracts.types import EventCategory, EventSeverity
from contracts.events import BaseEvent


class EventService(BaseService):
    """
    Central Event Store Service.

    ALL events in the system MUST be stored through this service.
    This provides:
    - Idempotent event storage (duplicate event_id rejected)
    - Category-based filtering
    - Time-based queries
    - User/device scoping

    RULE: This service does NOT handle evidence or decisions.
          Use EvidenceService for EMERGENCY evidence.
          Use DecisionService for AI decisions.
    """

    def store_event(self, event: BaseEvent, user_id: int = None, device_id: int = None) -> Optional[str]:
        """
        Store an event in the event store.

        Args:
            event: BaseEvent instance (or subclass)
            user_id: Optional user context
            device_id: Optional device context

        Returns:
            event_id if successful, None if failed or duplicate

        IDEMPOTENCY: If event_id already exists, returns None (not an error)
        """
        # Check for duplicate
        if self.exists("events", "event_id", event.event_id):
            return None  # Idempotent - already stored

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

        return event.event_id if result else None

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
