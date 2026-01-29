# ===============================
# services/dispatcher.py - Event Dispatcher (PRODUCTION)
# ===============================
# Central event routing with pub/sub pattern
#
# This is the NERVE CENTER of event-driven architecture.
# All events flow through here for:
# 1. Storage (EventService)
# 2. Evidence preservation (EvidenceService for EMERGENCY)
# 3. Handler routing (registered handlers)
# 4. Decision logging (DecisionService)

import time
from typing import Callable, Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum

from contracts.types import EventCategory, EventSeverity, IMMUTABLE_CATEGORIES
from contracts.events import BaseEvent, EmergencyEvent


class HandlerPriority(Enum):
    """Handler execution priority."""
    CRITICAL = 0   # Run first (e.g., evidence storage)
    HIGH = 10      # Important handlers
    NORMAL = 50    # Standard handlers
    LOW = 100      # Non-essential handlers


@dataclass
class HandlerRegistration:
    """Registration info for an event handler."""
    handler: Callable[[BaseEvent], None]
    name: str
    event_types: Set[str]  # Empty set = all events
    categories: Set[EventCategory]  # Empty set = all categories
    priority: HandlerPriority = HandlerPriority.NORMAL
    enabled: bool = True


class EventDispatcher:
    """
    Central Event Dispatcher.

    Responsibilities:
    1. Accept events from any source (Edge, Backend, User action)
    2. Store events in EventService
    3. Store evidence for EMERGENCY events in EvidenceService
    4. Route events to registered handlers
    5. Track handler execution for debugging

    Usage:
        dispatcher = EventDispatcher(event_service, evidence_service, decision_service)

        # Register handlers
        dispatcher.register_handler(
            name="emergency_alerter",
            handler=my_alert_function,
            categories={EventCategory.EMERGENCY},
            priority=HandlerPriority.HIGH
        )

        # Dispatch event
        dispatcher.dispatch(my_event, user_id=123)

    Thread Safety:
        This implementation is NOT thread-safe.
        For production, consider adding locks or using a proper message queue.
    """

    def __init__(
        self,
        event_service,
        evidence_service,
        decision_service
    ):
        self.event_service = event_service
        self.evidence_service = evidence_service
        self.decision_service = decision_service
        self._handlers: List[HandlerRegistration] = []
        self._dispatch_log: List[Dict[str, Any]] = []  # Recent dispatch history
        self._max_log_size = 1000

    def register_handler(
        self,
        name: str,
        handler: Callable[[BaseEvent], None],
        event_types: Set[str] = None,
        categories: Set[EventCategory] = None,
        priority: HandlerPriority = HandlerPriority.NORMAL,
    ) -> None:
        """
        Register an event handler.

        Args:
            name: Unique name for this handler (for debugging)
            handler: Callable that takes BaseEvent and returns None
            event_types: Set of event type names to handle (None = all)
            categories: Set of categories to handle (None = all)
            priority: Execution priority (CRITICAL runs first)

        Example:
            dispatcher.register_handler(
                name="energy_anomaly_detector",
                handler=detect_energy_anomaly,
                event_types={"EnergyUsageReported"},
                priority=HandlerPriority.HIGH
            )
        """
        registration = HandlerRegistration(
            handler=handler,
            name=name,
            event_types=event_types or set(),
            categories=categories or set(),
            priority=priority,
            enabled=True,
        )

        # Insert in priority order
        inserted = False
        for i, existing in enumerate(self._handlers):
            if registration.priority.value < existing.priority.value:
                self._handlers.insert(i, registration)
                inserted = True
                break

        if not inserted:
            self._handlers.append(registration)

        print(f"[DISPATCHER] Registered handler: {name} | Priority: {priority.name}")

    def unregister_handler(self, name: str) -> bool:
        """Remove a handler by name."""
        for i, reg in enumerate(self._handlers):
            if reg.name == name:
                self._handlers.pop(i)
                print(f"[DISPATCHER] Unregistered handler: {name}")
                return True
        return False

    def enable_handler(self, name: str) -> bool:
        """Enable a handler by name."""
        for reg in self._handlers:
            if reg.name == name:
                reg.enabled = True
                return True
        return False

    def disable_handler(self, name: str) -> bool:
        """Disable a handler by name."""
        for reg in self._handlers:
            if reg.name == name:
                reg.enabled = False
                return True
        return False

    def dispatch(
        self,
        event: BaseEvent,
        user_id: int = None,
        device_id: int = None,
        raw_evidence: bytes = None,
        evidence_type: str = None,
    ) -> Dict[str, Any]:
        """
        Dispatch an event through the system.

        This method:
        1. Stores the event in EventService
        2. If EMERGENCY, stores evidence in EvidenceService
        3. Routes to all matching handlers
        4. Returns dispatch result

        Args:
            event: The event to dispatch
            user_id: Optional user context
            device_id: Optional device context
            raw_evidence: Binary evidence (for EMERGENCY events)
            evidence_type: Type of evidence

        Returns:
            {
                "event_id": str,
                "stored": bool,
                "evidence_stored": bool or None,
                "handlers_called": int,
                "handler_results": [{name, success, error}],
                "elapsed_ms": float
            }
        """
        start_time = time.time()
        result = {
            "event_id": event.event_id,
            "stored": False,
            "evidence_stored": None,
            "handlers_called": 0,
            "handler_results": [],
            "elapsed_ms": 0,
        }

        # 1. Store event
        stored_id = self.event_service.store_event(event, user_id, device_id)
        result["stored"] = stored_id is not None

        # 2. Store evidence for EMERGENCY events
        if event.category in IMMUTABLE_CATEGORIES:
            evidence_id = self.evidence_service.store_evidence(
                event,
                raw_evidence=raw_evidence,
                evidence_type=evidence_type
            )
            result["evidence_stored"] = evidence_id is not None

        # 3. Route to handlers
        for registration in self._handlers:
            if not registration.enabled:
                continue

            # Check if handler should receive this event
            if registration.event_types and event.event_type not in registration.event_types:
                continue
            if registration.categories and event.category not in registration.categories:
                continue

            # Execute handler
            handler_result = {"name": registration.name, "success": False, "error": None}
            try:
                registration.handler(event)
                handler_result["success"] = True
            except Exception as e:
                handler_result["error"] = str(e)
                print(f"[DISPATCHER ERROR] Handler {registration.name} failed: {e}")

            result["handler_results"].append(handler_result)
            result["handlers_called"] += 1

        # 4. Calculate elapsed time
        result["elapsed_ms"] = (time.time() - start_time) * 1000

        # 5. Log dispatch
        self._log_dispatch(result)

        return result

    def dispatch_batch(
        self,
        events: List[BaseEvent],
        user_id: int = None,
        device_id: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Dispatch multiple events.

        Use for bulk event processing (e.g., batch sensor data).
        """
        return [
            self.dispatch(event, user_id, device_id)
            for event in events
        ]

    def _log_dispatch(self, result: Dict[str, Any]) -> None:
        """Log dispatch result for debugging."""
        self._dispatch_log.append({
            "timestamp": int(time.time()),
            **result
        })

        # Trim log if too large
        if len(self._dispatch_log) > self._max_log_size:
            self._dispatch_log = self._dispatch_log[-self._max_log_size:]

    def get_handler_info(self) -> List[Dict[str, Any]]:
        """Get info about registered handlers."""
        return [
            {
                "name": reg.name,
                "event_types": list(reg.event_types) if reg.event_types else "all",
                "categories": [c.value for c in reg.categories] if reg.categories else "all",
                "priority": reg.priority.name,
                "enabled": reg.enabled,
            }
            for reg in self._handlers
        ]

    def get_dispatch_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent dispatch history."""
        return self._dispatch_log[-limit:]

    def get_dispatch_stats(self) -> Dict[str, Any]:
        """Get dispatch statistics."""
        if not self._dispatch_log:
            return {
                "total_dispatches": 0,
                "avg_elapsed_ms": 0,
                "handlers_registered": len(self._handlers),
            }

        total = len(self._dispatch_log)
        avg_elapsed = sum(d["elapsed_ms"] for d in self._dispatch_log) / total

        return {
            "total_dispatches": total,
            "avg_elapsed_ms": round(avg_elapsed, 2),
            "handlers_registered": len(self._handlers),
            "handlers_enabled": sum(1 for h in self._handlers if h.enabled),
        }


# ===============================
# DEFAULT HANDLERS
# ===============================
# These handlers are automatically registered when dispatcher is created

def create_default_handlers(dispatcher: EventDispatcher) -> None:
    """
    Register default handlers that should always be active.

    Call this after creating the dispatcher.
    """

    # Emergency logger - always log emergencies to console
    def emergency_logger(event: BaseEvent):
        print(f"[EMERGENCY] {event.event_type} | ID: {event.event_id} | Severity: {event.severity.value}")

    dispatcher.register_handler(
        name="emergency_logger",
        handler=emergency_logger,
        categories={EventCategory.EMERGENCY},
        priority=HandlerPriority.CRITICAL,
    )

    # Anomaly logger
    def anomaly_logger(event: BaseEvent):
        print(f"[ANOMALY] {event.event_type} | ID: {event.event_id}")

    dispatcher.register_handler(
        name="anomaly_logger",
        handler=anomaly_logger,
        categories={EventCategory.ANOMALY},
        priority=HandlerPriority.HIGH,
    )

    print("[DISPATCHER] Default handlers registered")
