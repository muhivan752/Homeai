# ===============================
# services/decision.py - Decision Record Service (PRODUCTION)
# ===============================
# CRITICAL: Every automated decision MUST be logged here
#
# This service answers the question:
# "WHY did the system decide to do X?"
#
# Every escalation, alert, auto-action must have a decision record.

import json
import time
import uuid
import logging
from typing import Optional, List, Dict, Any, Union

from services.base import BaseService
from contracts.types import DecisionType, ActorType


# Structured logging
logger = logging.getLogger("homeai.decision")


class DecisionService(BaseService):
    """
    Decision Record Service.

    Every time the system makes an autonomous decision, it MUST be logged here.
    This is critical for:
    1. Debugging - understanding system behavior
    2. Legal - proving system acted reasonably
    3. Trust - showing users why actions were taken
    4. Audit - compliance and accountability

    Examples of decisions that MUST be logged:
    - Sending alert to user
    - Calling emergency services
    - Disabling a device automatically
    - Escalating to family member
    - Triggering lockdown

    VOCABULARY CONSTRAINTS:
    - decision_type: MUST be DecisionType enum value
    - actor_type: MUST be ActorType enum value
    - action_taken: Free text but should be descriptive
    """

    def _generate_decision_id(self) -> str:
        """Generate unique decision ID."""
        return f"dec_{uuid.uuid4().hex[:12]}"

    def _validate_decision_type(self, decision_type: Union[DecisionType, str]) -> str:
        """Validate and convert decision_type to string."""
        if isinstance(decision_type, DecisionType):
            return decision_type.value
        if isinstance(decision_type, str):
            # Validate it's a valid enum value
            valid_values = {e.value for e in DecisionType}
            if decision_type not in valid_values:
                raise ValueError(
                    f"Invalid decision_type: {decision_type}. "
                    f"Must be one of: {valid_values}"
                )
            return decision_type
        raise TypeError(f"decision_type must be DecisionType or str, got {type(decision_type)}")

    def _validate_actor_type(self, actor_type: Union[ActorType, str]) -> str:
        """Validate and convert actor_type to string."""
        if isinstance(actor_type, ActorType):
            return actor_type.value
        if isinstance(actor_type, str):
            # Validate it's a valid enum value
            valid_values = {e.value for e in ActorType}
            if actor_type not in valid_values:
                raise ValueError(
                    f"Invalid actor_type: {actor_type}. "
                    f"Must be one of: {valid_values}"
                )
            return actor_type
        raise TypeError(f"actor_type must be ActorType or str, got {type(actor_type)}")

    def log_decision(
        self,
        trigger_event_id: str,
        trigger_event_type: str,
        decision_type: Union[DecisionType, str],
        action_taken: str,
        reason: str,
        actor_type: Union[ActorType, str] = ActorType.SYSTEM,
        actor_id: int = None,
        confidence: float = None,
        model_name: str = None,
        model_version: str = None,
    ) -> Optional[str]:
        """
        Log an automated decision.

        Args:
            trigger_event_id: The event that triggered this decision
            trigger_event_type: Type of trigger event
            decision_type: Category of decision (MUST be DecisionType)
            action_taken: What action was taken (human readable)
            reason: Why this decision was made (human readable)
            actor_type: Who/what made the decision (MUST be ActorType)
            actor_id: Optional ID of the actor (e.g., user_id if admin override)
            confidence: Model confidence score (0.0 - 1.0) if ML-based
            model_name: Name of the model that made the decision
            model_version: Version of the model

        Returns:
            decision_id if successful, None if failed

        Raises:
            ValueError: If decision_type or actor_type is invalid

        Example:
            decision_service.log_decision(
                trigger_event_id="evt_abc123",
                trigger_event_type="IntrusionDetected",
                decision_type=DecisionType.CALL_EMERGENCY,
                action_taken="Called 911 emergency services",
                reason="Unknown person at front door, owner unreachable for 5 minutes",
                actor_type=ActorType.MODEL,
                confidence=0.95,
                model_name="face_recognition_v2",
                model_version="2.3.1"
            )
        """
        # Validate constrained fields
        decision_type_str = self._validate_decision_type(decision_type)
        actor_type_str = self._validate_actor_type(actor_type)

        decision_id = self._generate_decision_id()
        now = int(time.time())

        result = self.run_query(
            """
            INSERT INTO decision_records
            (decision_id, trigger_event_id, trigger_event_type, decision_type,
             action_taken, reason, confidence, model_name, model_version,
             actor_type, actor_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                trigger_event_id,
                trigger_event_type,
                decision_type_str,
                action_taken,
                reason,
                confidence,
                model_name,
                model_version,
                actor_type_str,
                actor_id,
                now,
            ),
            commit=True
        )

        if result:
            logger.info(
                "Decision logged: %s | Type: %s | Actor: %s | Event: %s",
                decision_id, decision_type_str, actor_type_str, trigger_event_id
            )
            return decision_id

        logger.error("Failed to log decision for event %s", trigger_event_id)
        return None

    def log_no_action_decision(
        self,
        trigger_event_id: str,
        trigger_event_type: str,
        reason: str,
        actor_type: Union[ActorType, str] = ActorType.SYSTEM,
        confidence: float = None,
    ) -> Optional[str]:
        """
        Log a decision to NOT take action.

        This is equally important as logging actions.
        "Why DIDN'T the system alert me?" is a valid question.

        Args:
            trigger_event_id: The event that was evaluated
            trigger_event_type: Type of trigger event
            reason: Why no action was taken
            actor_type: Who/what made the decision
            confidence: Confidence in the no-action decision

        Returns:
            decision_id if successful
        """
        return self.log_decision(
            trigger_event_id=trigger_event_id,
            trigger_event_type=trigger_event_type,
            decision_type=DecisionType.NO_ACTION,
            action_taken="No action taken",
            reason=reason,
            actor_type=actor_type,
            confidence=confidence,
        )

    def update_outcome(
        self,
        decision_id: str,
        outcome: str,
    ) -> bool:
        """
        Update the outcome of a decision.

        Call this after the action has been executed to record the result.

        Args:
            decision_id: The decision to update
            outcome: What happened as a result ("success", "failed", "partial", etc.)

        Returns:
            True if updated, False if not found or error
        """
        now = int(time.time())
        result = self.run_query(
            """
            UPDATE decision_records
            SET outcome = ?, outcome_at = ?
            WHERE decision_id = ?
            """,
            (outcome, now, decision_id),
            commit=True
        )

        if result and result > 0:
            logger.debug("Decision %s outcome updated: %s", decision_id, outcome)
            return True

        logger.warning("Failed to update outcome for decision %s", decision_id)
        return False

    def get_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """Get single decision by ID."""
        return self.run_query(
            "SELECT * FROM decision_records WHERE decision_id = ?",
            (decision_id,),
            one=True
        )

    def get_decisions_for_event(self, event_id: str) -> List[Dict[str, Any]]:
        """Get all decisions made in response to an event."""
        return self.run_query(
            """
            SELECT * FROM decision_records
            WHERE trigger_event_id = ?
            ORDER BY created_at DESC
            """,
            (event_id,)
        ) or []

    def get_decisions_by_type(
        self,
        decision_type: Union[DecisionType, str],
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get decisions filtered by type."""
        decision_type_str = self._validate_decision_type(decision_type)
        return self.run_query(
            """
            SELECT * FROM decision_records
            WHERE decision_type = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (decision_type_str, limit)
        ) or []

    def get_decisions_by_actor(
        self,
        actor_type: Union[ActorType, str],
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get decisions filtered by actor type."""
        actor_type_str = self._validate_actor_type(actor_type)
        return self.run_query(
            """
            SELECT * FROM decision_records
            WHERE actor_type = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (actor_type_str, limit)
        ) or []

    def get_recent_decisions(
        self,
        limit: int = 100,
        since_timestamp: int = None
    ) -> List[Dict[str, Any]]:
        """Get recent decisions."""
        if since_timestamp:
            return self.run_query(
                """
                SELECT * FROM decision_records
                WHERE created_at > ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (since_timestamp, limit)
            ) or []
        else:
            return self.run_query(
                """
                SELECT * FROM decision_records
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,)
            ) or []

    def get_emergency_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get decisions related to emergency events."""
        return self.run_query(
            """
            SELECT dr.* FROM decision_records dr
            JOIN events e ON dr.trigger_event_id = e.event_id
            WHERE e.category = 'emergency'
            ORDER BY dr.created_at DESC
            LIMIT ?
            """,
            (limit,)
        ) or []

    def get_decision_stats(self) -> Dict[str, Any]:
        """Get statistics about decisions."""
        total = self.run_query(
            "SELECT COUNT(*) as c FROM decision_records",
            one=True
        )

        by_type = self.run_query(
            """
            SELECT decision_type, COUNT(*) as count
            FROM decision_records
            GROUP BY decision_type
            """
        )

        by_actor = self.run_query(
            """
            SELECT actor_type, COUNT(*) as count
            FROM decision_records
            GROUP BY actor_type
            """
        )

        with_outcome = self.run_query(
            "SELECT COUNT(*) as c FROM decision_records WHERE outcome IS NOT NULL",
            one=True
        )

        return {
            "total_decisions": total['c'] if total else 0,
            "by_type": {r['decision_type']: r['count'] for r in (by_type or [])},
            "by_actor": {r['actor_type']: r['count'] for r in (by_actor or [])},
            "with_outcome": with_outcome['c'] if with_outcome else 0,
        }

    def explain_decision(self, decision_id: str) -> Optional[Dict[str, Any]]:
        """
        Get human-readable explanation of a decision.

        This is the method to call when user asks "Why did the system do X?"

        Returns:
            {
                "decision_id": str,
                "when": str (human readable),
                "trigger": str (what caused it),
                "decision": str (what was decided),
                "action": str (what action was taken),
                "reason": str (why),
                "actor": str (who decided),
                "confidence": float or None,
                "outcome": str or None
            }
        """
        decision = self.get_decision(decision_id)
        if not decision:
            return None

        from datetime import datetime
        when = datetime.fromtimestamp(decision['created_at']).strftime('%Y-%m-%d %H:%M:%S')

        explanation = {
            "decision_id": decision['decision_id'],
            "when": when,
            "trigger": f"{decision['trigger_event_type']} (event: {decision['trigger_event_id']})",
            "decision": decision['decision_type'],
            "action": decision['action_taken'],
            "reason": decision['reason'],
            "actor": f"{decision['actor_type']}" + (f" (id: {decision['actor_id']})" if decision.get('actor_id') else ""),
            "confidence": decision.get('confidence'),
            "outcome": decision.get('outcome'),
        }

        if decision.get('model_name'):
            explanation["model"] = f"{decision['model_name']} v{decision.get('model_version', 'N/A')}"

        return explanation
