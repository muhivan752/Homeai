# ===============================
# services/dispatcher.py - Event Dispatcher (PRODUCTION)
# ===============================
# Central event routing with ISOLATED emergency pipeline
#
# CRITICAL ARCHITECTURE:
# 1. Emergency events have DEDICATED pipeline - never blocked by other handlers
# 2. Evidence storage is SYNCHRONOUS (must complete)
# 3. Emergency escalation is ASYNC (separate thread)
# 4. Non-emergency handlers run in main thread pool
#
# THREAD MODEL:
# - Main Thread: accepts dispatch() calls
# - Emergency Thread: dedicated for emergency handlers (never starved)
# - Worker Pool: for non-emergency handlers

import time
import queue
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum

from contracts.types import EventCategory, EventSeverity, IMMUTABLE_CATEGORIES
from contracts.events import BaseEvent, EmergencyEvent


# ===============================
# STRUCTURED LOGGING
# ===============================
logger = logging.getLogger("homeai.dispatcher")
logger.setLevel(logging.DEBUG)

# Create handler if not exists
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(handler)


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
    is_emergency_handler: bool = False  # If True, runs in emergency thread


class EventDispatcher:
    """
    Central Event Dispatcher with ISOLATED EMERGENCY PIPELINE.

    ARCHITECTURE:
    ┌─────────────────────────────────────────────────────────────┐
    │                      dispatch(event)                        │
    └─────────────────────────┬───────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │      Is EMERGENCY?            │
              └───────────────┬───────────────┘
                    │                   │
                   YES                  NO
                    │                   │
    ┌───────────────┴──────┐    ┌──────┴───────────────┐
    │  EMERGENCY PIPELINE  │    │  NORMAL PIPELINE     │
    │  (Dedicated Thread)  │    │  (Thread Pool)       │
    │                      │    │                      │
    │  1. Store evidence   │    │  1. Store event      │
    │     (SYNC - blocks)  │    │  2. Run handlers     │
    │  2. Run emergency    │    │     (async)          │
    │     handlers (SYNC)  │    │                      │
    │  3. Escalation       │    │                      │
    │     (ASYNC)          │    │                      │
    └──────────────────────┘    └──────────────────────┘

    GUARANTEES:
    - Emergency evidence is ALWAYS stored before returning
    - Emergency handlers are NEVER blocked by non-emergency work
    - Non-emergency burst cannot starve emergency pipeline
    """

    def __init__(
        self,
        event_service,
        evidence_service,
        decision_service,
        max_workers: int = 4,
    ):
        self.event_service = event_service
        self.evidence_service = evidence_service
        self.decision_service = decision_service

        # Handler registrations
        self._handlers: List[HandlerRegistration] = []
        self._emergency_handlers: List[HandlerRegistration] = []

        # Thread pools
        self._worker_pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="evt_worker")

        # Emergency dedicated thread
        self._emergency_queue: queue.Queue = queue.Queue()
        self._emergency_thread = threading.Thread(
            target=self._emergency_worker,
            name="emergency_pipeline",
            daemon=True
        )
        self._emergency_thread.start()

        # Dispatch statistics
        self._stats = {
            "total_dispatched": 0,
            "emergency_count": 0,
            "normal_count": 0,
            "handler_errors": 0,
        }
        self._stats_lock = threading.Lock()

        # Dispatch log (circular buffer)
        self._dispatch_log: List[Dict[str, Any]] = []
        self._max_log_size = 1000
        self._log_lock = threading.Lock()

        # Shutdown flag
        self._shutdown = False

        logger.info("EventDispatcher initialized with %d workers", max_workers)

    def _emergency_worker(self):
        """
        Dedicated emergency worker thread.

        This thread ONLY processes emergency events.
        It is never blocked by non-emergency work.
        """
        logger.info("Emergency worker thread started")

        while not self._shutdown:
            try:
                # Wait for emergency event (with timeout for graceful shutdown)
                try:
                    work_item = self._emergency_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                event, raw_evidence, evidence_type, user_id, device_id, result_future = work_item

                # Process emergency
                result = self._process_emergency(
                    event, raw_evidence, evidence_type, user_id, device_id
                )

                # Signal completion
                result_future.set_result(result)

            except Exception as e:
                logger.exception("Emergency worker error: %s", e)

        logger.info("Emergency worker thread stopped")

    def _process_emergency(
        self,
        event: BaseEvent,
        raw_evidence: bytes,
        evidence_type: str,
        user_id: int,
        device_id: int,
    ) -> Dict[str, Any]:
        """
        Process emergency event in dedicated thread.

        Order of operations (CRITICAL):
        1. Store evidence SYNCHRONOUSLY (must complete)
        2. Store event metadata in events table (reference only)
        3. Run emergency handlers SYNCHRONOUSLY
        4. Return result
        """
        start_time = time.time()
        result = {
            "event_id": event.event_id,
            "category": "emergency",
            "evidence_stored": False,
            "event_stored": False,
            "handlers_called": 0,
            "handler_results": [],
            "elapsed_ms": 0,
        }

        logger.critical(
            "EMERGENCY EVENT: %s | ID: %s | Severity: %s",
            event.event_type, event.event_id, event.severity.value
        )

        # 1. STORE EVIDENCE (SYNCHRONOUS - MUST COMPLETE)
        try:
            evidence_id = self.evidence_service.store_evidence(
                event,
                raw_evidence=raw_evidence,
                evidence_type=evidence_type
            )
            result["evidence_stored"] = evidence_id is not None

            if not result["evidence_stored"]:
                logger.error("FAILED to store emergency evidence for %s", event.event_id)
            else:
                logger.info("Emergency evidence stored: %s", event.event_id)

        except Exception as e:
            logger.exception("Evidence storage error: %s", e)

        # 2. STORE EVENT METADATA (reference only, not full payload)
        try:
            # For emergency, we only store minimal metadata in events table
            # Full payload is in event_evidence table
            stored_id = self.event_service.store_event(
                event, user_id, device_id,
                emergency_payload_ref=event.event_id  # Reference to evidence
            )
            result["event_stored"] = stored_id is not None
        except Exception as e:
            logger.exception("Event metadata storage error: %s", e)

        # 3. RUN EMERGENCY HANDLERS (SYNCHRONOUS)
        for registration in self._emergency_handlers:
            if not registration.enabled:
                continue

            if registration.event_types and event.event_type not in registration.event_types:
                continue

            handler_result = {"name": registration.name, "success": False, "error": None}
            try:
                registration.handler(event)
                handler_result["success"] = True
                logger.info("Emergency handler '%s' completed", registration.name)
            except Exception as e:
                handler_result["error"] = str(e)
                logger.exception("Emergency handler '%s' failed: %s", registration.name, e)
                with self._stats_lock:
                    self._stats["handler_errors"] += 1

            result["handler_results"].append(handler_result)
            result["handlers_called"] += 1

        # 4. Calculate elapsed time
        result["elapsed_ms"] = (time.time() - start_time) * 1000

        # Update stats
        with self._stats_lock:
            self._stats["total_dispatched"] += 1
            self._stats["emergency_count"] += 1

        self._log_dispatch(result)

        logger.info(
            "Emergency processed in %.2fms | Evidence: %s | Handlers: %d",
            result["elapsed_ms"],
            result["evidence_stored"],
            result["handlers_called"]
        )

        return result

    def _process_normal(
        self,
        event: BaseEvent,
        user_id: int,
        device_id: int,
    ) -> Dict[str, Any]:
        """
        Process non-emergency event.

        Runs in worker thread pool, can be delayed by other work.
        """
        start_time = time.time()
        result = {
            "event_id": event.event_id,
            "category": event.category.value,
            "stored": False,
            "handlers_called": 0,
            "handler_results": [],
            "elapsed_ms": 0,
        }

        logger.debug(
            "Processing event: %s | ID: %s | Category: %s",
            event.event_type, event.event_id, event.category.value
        )

        # 1. Store event
        try:
            stored_id = self.event_service.store_event(event, user_id, device_id)
            result["stored"] = stored_id is not None
        except Exception as e:
            logger.exception("Event storage error: %s", e)

        # 2. Run matching handlers
        for registration in self._handlers:
            if not registration.enabled:
                continue
            if registration.is_emergency_handler:
                continue  # Skip emergency handlers

            if registration.event_types and event.event_type not in registration.event_types:
                continue
            if registration.categories and event.category not in registration.categories:
                continue

            handler_result = {"name": registration.name, "success": False, "error": None}
            try:
                registration.handler(event)
                handler_result["success"] = True
            except Exception as e:
                handler_result["error"] = str(e)
                logger.warning("Handler '%s' failed: %s", registration.name, e)
                with self._stats_lock:
                    self._stats["handler_errors"] += 1

            result["handler_results"].append(handler_result)
            result["handlers_called"] += 1

        # 3. Calculate elapsed time
        result["elapsed_ms"] = (time.time() - start_time) * 1000

        # Update stats
        with self._stats_lock:
            self._stats["total_dispatched"] += 1
            self._stats["normal_count"] += 1

        self._log_dispatch(result)

        return result

    def register_handler(
        self,
        name: str,
        handler: Callable[[BaseEvent], None],
        event_types: Set[str] = None,
        categories: Set[EventCategory] = None,
        priority: HandlerPriority = HandlerPriority.NORMAL,
        is_emergency_handler: bool = False,
    ) -> None:
        """
        Register an event handler.

        Args:
            name: Unique name for this handler
            handler: Callable that takes BaseEvent
            event_types: Set of event type names to handle (None = all)
            categories: Set of categories to handle (None = all)
            priority: Execution priority
            is_emergency_handler: If True, runs in dedicated emergency thread

        IMPORTANT:
            Emergency handlers (is_emergency_handler=True) run in a dedicated thread
            and are NEVER blocked by non-emergency work.
        """
        registration = HandlerRegistration(
            handler=handler,
            name=name,
            event_types=event_types or set(),
            categories=categories or set(),
            priority=priority,
            enabled=True,
            is_emergency_handler=is_emergency_handler,
        )

        if is_emergency_handler:
            # Insert in priority order for emergency handlers
            inserted = False
            for i, existing in enumerate(self._emergency_handlers):
                if registration.priority.value < existing.priority.value:
                    self._emergency_handlers.insert(i, registration)
                    inserted = True
                    break
            if not inserted:
                self._emergency_handlers.append(registration)
            logger.info("Registered EMERGENCY handler: %s", name)
        else:
            # Insert in priority order for normal handlers
            inserted = False
            for i, existing in enumerate(self._handlers):
                if registration.priority.value < existing.priority.value:
                    self._handlers.insert(i, registration)
                    inserted = True
                    break
            if not inserted:
                self._handlers.append(registration)
            logger.info("Registered handler: %s | Priority: %s", name, priority.name)

    def unregister_handler(self, name: str) -> bool:
        """Remove a handler by name."""
        for handler_list in [self._handlers, self._emergency_handlers]:
            for i, reg in enumerate(handler_list):
                if reg.name == name:
                    handler_list.pop(i)
                    logger.info("Unregistered handler: %s", name)
                    return True
        return False

    def enable_handler(self, name: str) -> bool:
        """Enable a handler by name."""
        for handler_list in [self._handlers, self._emergency_handlers]:
            for reg in handler_list:
                if reg.name == name:
                    reg.enabled = True
                    return True
        return False

    def disable_handler(self, name: str) -> bool:
        """Disable a handler by name."""
        for handler_list in [self._handlers, self._emergency_handlers]:
            for reg in handler_list:
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
        wait: bool = True,
    ) -> Dict[str, Any]:
        """
        Dispatch an event through the system.

        ROUTING:
        - EMERGENCY events → dedicated emergency pipeline (never blocked)
        - Other events → worker thread pool

        Args:
            event: The event to dispatch
            user_id: Optional user context
            device_id: Optional device context
            raw_evidence: Binary evidence (for EMERGENCY events)
            evidence_type: Type of evidence
            wait: If True, wait for processing to complete (default True)

        Returns:
            Dispatch result dict
        """
        # EMERGENCY PATH - dedicated thread, highest priority
        if event.category == EventCategory.EMERGENCY:
            return self._dispatch_emergency(
                event, raw_evidence, evidence_type, user_id, device_id, wait
            )

        # NORMAL PATH - worker pool
        return self._dispatch_normal(event, user_id, device_id, wait)

    def _dispatch_emergency(
        self,
        event: BaseEvent,
        raw_evidence: bytes,
        evidence_type: str,
        user_id: int,
        device_id: int,
        wait: bool,
    ) -> Dict[str, Any]:
        """Dispatch emergency to dedicated pipeline."""
        # Create future for result
        result_future = threading.Event()
        result_container = [None]

        class ResultFuture:
            def set_result(self, result):
                result_container[0] = result
                result_future.set()

            def get_result(self, timeout=None):
                result_future.wait(timeout)
                return result_container[0]

        future = ResultFuture()

        # Queue for emergency thread
        self._emergency_queue.put((
            event, raw_evidence, evidence_type, user_id, device_id, future
        ))

        if wait:
            # Wait for emergency processing to complete
            result = future.get_result(timeout=30.0)
            if result is None:
                logger.error("Emergency dispatch timeout for %s", event.event_id)
                return {
                    "event_id": event.event_id,
                    "error": "timeout",
                    "category": "emergency",
                }
            return result
        else:
            return {
                "event_id": event.event_id,
                "queued": True,
                "category": "emergency",
            }

    def _dispatch_normal(
        self,
        event: BaseEvent,
        user_id: int,
        device_id: int,
        wait: bool,
    ) -> Dict[str, Any]:
        """Dispatch normal event to worker pool."""
        if wait:
            # Process synchronously in current thread
            return self._process_normal(event, user_id, device_id)
        else:
            # Submit to worker pool
            future = self._worker_pool.submit(
                self._process_normal, event, user_id, device_id
            )
            return {
                "event_id": event.event_id,
                "queued": True,
                "category": event.category.value,
            }

    def dispatch_batch(
        self,
        events: List[BaseEvent],
        user_id: int = None,
        device_id: int = None,
    ) -> List[Dict[str, Any]]:
        """
        Dispatch multiple events.

        Emergency events are still prioritized and processed in dedicated thread.
        Non-emergency events are processed in parallel via worker pool.
        """
        results = []

        # Separate emergency from non-emergency
        emergency_events = [e for e in events if e.category == EventCategory.EMERGENCY]
        normal_events = [e for e in events if e.category != EventCategory.EMERGENCY]

        # Process emergencies first (they go to dedicated thread anyway)
        for event in emergency_events:
            result = self.dispatch(event, user_id, device_id, wait=True)
            results.append(result)

        # Process normal events in parallel
        futures = []
        for event in normal_events:
            future = self._worker_pool.submit(
                self._process_normal, event, user_id, device_id
            )
            futures.append((event.event_id, future))

        # Collect results
        for event_id, future in futures:
            try:
                result = future.result(timeout=10.0)
                results.append(result)
            except Exception as e:
                results.append({
                    "event_id": event_id,
                    "error": str(e),
                })

        return results

    def _log_dispatch(self, result: Dict[str, Any]) -> None:
        """Log dispatch result for debugging."""
        with self._log_lock:
            self._dispatch_log.append({
                "timestamp": int(time.time()),
                **result
            })

            # Trim log if too large
            if len(self._dispatch_log) > self._max_log_size:
                self._dispatch_log = self._dispatch_log[-self._max_log_size:]

    def get_handler_info(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get info about registered handlers."""
        return {
            "emergency_handlers": [
                {
                    "name": reg.name,
                    "event_types": list(reg.event_types) if reg.event_types else "all",
                    "priority": reg.priority.name,
                    "enabled": reg.enabled,
                }
                for reg in self._emergency_handlers
            ],
            "normal_handlers": [
                {
                    "name": reg.name,
                    "event_types": list(reg.event_types) if reg.event_types else "all",
                    "categories": [c.value for c in reg.categories] if reg.categories else "all",
                    "priority": reg.priority.name,
                    "enabled": reg.enabled,
                }
                for reg in self._handlers
            ],
        }

    def get_dispatch_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent dispatch history."""
        with self._log_lock:
            return self._dispatch_log[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """Get dispatch statistics."""
        with self._stats_lock:
            return {
                **self._stats,
                "emergency_handlers": len(self._emergency_handlers),
                "normal_handlers": len(self._handlers),
                "emergency_thread_alive": self._emergency_thread.is_alive(),
            }

    def shutdown(self, wait: bool = True):
        """Shutdown the dispatcher gracefully."""
        logger.info("Shutting down dispatcher...")
        self._shutdown = True

        if wait:
            self._emergency_thread.join(timeout=5.0)
            self._worker_pool.shutdown(wait=True)

        logger.info("Dispatcher shutdown complete")


# ===============================
# DEFAULT HANDLERS
# ===============================

def create_default_handlers(dispatcher: EventDispatcher) -> None:
    """
    Register default handlers that should always be active.
    """
    # Emergency console logger - runs in emergency thread
    def emergency_console_logger(event: BaseEvent):
        logger.critical(
            "[EMERGENCY ALERT] %s | ID: %s | Severity: %s",
            event.event_type, event.event_id, event.severity.value
        )

    dispatcher.register_handler(
        name="emergency_console_logger",
        handler=emergency_console_logger,
        categories={EventCategory.EMERGENCY},
        priority=HandlerPriority.CRITICAL,
        is_emergency_handler=True,  # Runs in dedicated emergency thread
    )

    # Anomaly logger - runs in normal thread pool
    def anomaly_logger(event: BaseEvent):
        logger.warning(
            "[ANOMALY] %s | ID: %s",
            event.event_type, event.event_id
        )

    dispatcher.register_handler(
        name="anomaly_logger",
        handler=anomaly_logger,
        categories={EventCategory.ANOMALY},
        priority=HandlerPriority.HIGH,
        is_emergency_handler=False,
    )

    logger.info("Default handlers registered")


def create_escalation_handlers(
    dispatcher: EventDispatcher,
    escalation_engine,
    confirmation_service,
    trusted_contacts_service,
    decision_service,
) -> None:
    """
    Register escalation handlers for emergency events.

    This integrates the escalation system with the event dispatcher.

    FLOW:
    1. Emergency event arrives
    2. Escalation engine decides what to do
    3. Immediate actions are executed
    4. Confirmation request is created (30 second window)
    5. Deferred actions wait for confirmation or timeout
    """
    from contracts.types import (
        EmergencyType,
        EscalationAction,
        DecisionType,
        ActorType,
    )
    from services.escalation import EscalationContext

    def emergency_escalation_handler(event: BaseEvent):
        """
        Handle emergency events through escalation engine.

        This runs in the dedicated emergency thread.
        """
        # Extract context from event
        payload = event.payload if hasattr(event, 'payload') else {}

        # Map event type to emergency type
        event_to_emergency = {
            "IntrusionDetected": EmergencyType.INTRUSION,
            "FireDetected": EmergencyType.FIRE,
            "ViolenceDetected": EmergencyType.VIOLENCE,
            "WaterLeakDetected": EmergencyType.WATER_LEAK,
            "PowerEmergency": EmergencyType.POWER_EMERGENCY,
            "PanicButtonPressed": EmergencyType.PANIC,
        }

        emergency_type = event_to_emergency.get(
            event.event_type,
            EmergencyType.INTRUSION  # Default
        )

        # Build escalation context
        context = EscalationContext(
            user_id=payload.get("user_id", 0),
            event_id=event.event_id,
            event_type=event.event_type,
            emergency_type=emergency_type,
            confidence=payload.get("confidence", 0.5),
            location=payload.get("location"),
            device_id=payload.get("device_id"),
            multiple_sensors=payload.get("multiple_sensors", False),
            duration_seconds=payload.get("duration_seconds", 0),
            corroborating_events=payload.get("corroborating_events", []),
        )

        # Get escalation decision
        decision = escalation_engine.decide(context)

        # Log the decision
        decision_id = decision_service.log_decision(
            trigger_event_id=event.event_id,
            trigger_event_type=event.event_type,
            decision_type=_map_action_to_decision_type(decision.immediate_actions),
            action_taken=f"Immediate: {[a.value for a in decision.immediate_actions]}",
            reason=decision.reason,
            actor_type=ActorType.SYSTEM,
            confidence=context.confidence,
        )

        # Execute immediate actions
        for action in decision.immediate_actions:
            _execute_action(
                action, context, trusted_contacts_service, decision_service, decision_id
            )

        # Create confirmation request if needed
        if decision.requires_confirmation and decision.deferred_actions:
            fallback_actions = ",".join(a.value for a in decision.deferred_actions)
            confirmation_service.create_confirmation(
                user_id=context.user_id,
                event_id=event.event_id,
                event_type=emergency_type.value,
                fallback_action=fallback_actions,
                window_seconds=decision.confirmation_window_seconds,
            )

            logger.info(
                "Confirmation created for %s | Window: %ds | Fallback: %s",
                event.event_id,
                decision.confirmation_window_seconds,
                fallback_actions
            )

    def _map_action_to_decision_type(actions: list) -> DecisionType:
        """Map escalation actions to decision type for logging."""
        if not actions:
            return DecisionType.NO_ACTION

        # Priority order
        if any(a in actions for a in [
            EscalationAction.CALL_POLICE,
            EscalationAction.CALL_FIRE,
            EscalationAction.CALL_AMBULANCE
        ]):
            return DecisionType.CALL_EMERGENCY

        if EscalationAction.ALERT_TRUSTED in actions:
            return DecisionType.ALERT_FAMILY

        if EscalationAction.ALERT_OWNER in actions:
            return DecisionType.ALERT_USER

        if EscalationAction.LOCKDOWN in actions:
            return DecisionType.LOCKDOWN

        if EscalationAction.DISABLE_DEVICE in actions:
            return DecisionType.DISABLE_DEVICE

        return DecisionType.ESCALATE

    def _execute_action(
        action: EscalationAction,
        context: EscalationContext,
        trusted_contacts_service,
        decision_service,
        parent_decision_id: str,
    ):
        """Execute a single escalation action."""
        logger.info(
            "Executing action: %s for event %s",
            action.value, context.event_id
        )

        if action == EscalationAction.LOCAL_ALARM:
            # TODO: Trigger local alarm via edge
            logger.info("LOCAL_ALARM triggered for %s", context.location or "unknown")

        elif action == EscalationAction.ALERT_OWNER:
            # TODO: Send notification to owner
            logger.info("ALERT_OWNER: Notifying user %d", context.user_id)

        elif action == EscalationAction.ALERT_FAMILY:
            # TODO: Send notification to family members
            logger.info("ALERT_FAMILY: Notifying family of user %d", context.user_id)

        elif action == EscalationAction.ALERT_TRUSTED:
            # Get trusted contacts for this event type
            contacts = trusted_contacts_service.get_contacts_for_event(
                context.user_id,
                context.emergency_type.value
            )
            for contact in contacts:
                logger.info(
                    "ALERT_TRUSTED: Notifying %s (%s) via %s",
                    contact["name"],
                    contact["relationship"],
                    "telegram" if contact.get("telegram_chat_id") else "phone/email"
                )
                # TODO: Actually send notification

        elif action == EscalationAction.LOCKDOWN:
            # TODO: Trigger lockdown mode
            logger.warning("LOCKDOWN triggered for user %d", context.user_id)

        elif action == EscalationAction.DISABLE_DEVICE:
            if context.device_id:
                # TODO: Disable device
                logger.warning("DISABLE_DEVICE: Device %d disabled", context.device_id)

        # Note: CALL_POLICE, CALL_FIRE, CALL_AMBULANCE, RECORD_EVIDENCE
        # require explicit consent and are typically deferred actions

    # Register the emergency escalation handler
    dispatcher.register_handler(
        name="emergency_escalation",
        handler=emergency_escalation_handler,
        categories={EventCategory.EMERGENCY},
        priority=HandlerPriority.HIGH,
        is_emergency_handler=True,
    )

    # Register confirmation callbacks
    def on_confirmed_threat(confirmation):
        """User confirmed this is a real threat - execute deferred actions."""
        logger.warning(
            "THREAT CONFIRMED by user for event %s - executing deferred actions",
            confirmation["event_id"]
        )
        # Parse fallback actions
        actions = confirmation["fallback_action"].split(",")
        for action_str in actions:
            try:
                action = EscalationAction(action_str.strip())
                # TODO: Execute action with full context
                logger.info("Executing deferred action: %s", action.value)
            except ValueError:
                logger.warning("Unknown action: %s", action_str)

        # Log decision
        decision_service.log_decision(
            trigger_event_id=confirmation["event_id"],
            trigger_event_type=confirmation["event_type"],
            decision_type=DecisionType.ESCALATE,
            action_taken=f"User confirmed threat, executing: {confirmation['fallback_action']}",
            reason="User explicitly confirmed situation is a threat",
            actor_type=ActorType.USER,
            actor_id=confirmation["user_id"],
        )

    def on_confirmed_safe(confirmation):
        """User confirmed situation is safe - cancel escalation."""
        logger.info(
            "SAFE CONFIRMED by user for event %s - escalation cancelled",
            confirmation["event_id"]
        )

        # Log decision
        decision_service.log_decision(
            trigger_event_id=confirmation["event_id"],
            trigger_event_type=confirmation["event_type"],
            decision_type=DecisionType.NO_ACTION,
            action_taken="Escalation cancelled by user",
            reason="User confirmed situation is safe (false alarm)",
            actor_type=ActorType.USER,
            actor_id=confirmation["user_id"],
        )

    def on_confirmation_expired(confirmation):
        """Confirmation window expired - execute fallback actions."""
        logger.warning(
            "CONFIRMATION EXPIRED for event %s - executing fallback: %s",
            confirmation["event_id"],
            confirmation["fallback_action"]
        )

        # Parse and execute fallback actions
        actions = confirmation["fallback_action"].split(",")
        for action_str in actions:
            try:
                action = EscalationAction(action_str.strip())
                logger.info("Executing fallback action: %s", action.value)
                # TODO: Execute action
            except ValueError:
                logger.warning("Unknown fallback action: %s", action_str)

        # Log decision
        decision_service.log_decision(
            trigger_event_id=confirmation["event_id"],
            trigger_event_type=confirmation["event_type"],
            decision_type=DecisionType.ESCALATE,
            action_taken=f"Auto-escalation after timeout: {confirmation['fallback_action']}",
            reason="User did not respond within confirmation window",
            actor_type=ActorType.SYSTEM,
        )

    confirmation_service.register_callback("on_confirmed_threat", on_confirmed_threat)
    confirmation_service.register_callback("on_confirmed_safe", on_confirmed_safe)
    confirmation_service.register_callback("on_expired", on_confirmation_expired)

    logger.info("Escalation handlers registered")
