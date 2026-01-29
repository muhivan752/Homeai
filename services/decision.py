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
from typing import Optional, List, Dict, Any

from services.base import BaseService
from contracts.types import DecisionType, EventSource


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
    """

    def _generate_decision_id(self) -> str:
        """Generate unique decision ID."""
        return f"dec_{uuid.uuid4().hex[:12]}"

    def log_decision(
        self,
        trigger_event_id: str,
        trigger_event_type: str,
        decision_type: DecisionType,
        action_taken: str,
        reason: str,
        actor_type: str = "system",
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
            decision_type: Category of decision (from DecisionType enum)
            action_taken: What action was taken (human readable)
            reason: Why this decision was made (human readable)
            actor_type: Who/what made the decision ("system", "model", "rule")
            actor_id: Optional ID of the actor (e.g., user_id if admin override)
            confidence: Model confidence score (0.0 - 1.0) if ML-based
            model_name: Name of the model that made the decision
            model_version: Version of the model

        Returns:
            decision_id if successful, None if failed

        Example:
            decision_service.log_decision(
                trigger_event_id="evt_abc123",
                trigger_event_type="IntrusionDetected",
                decision_type=DecisionType.CALL_EMERGENCY,
                action_taken="Called 911 emergency services",
                reason="Unknown person detected at front door with 95% confidence, owner unreachable for 5 minutes",
                confidence=0.95,
                model_name="face_recognition_v2",
                model_version="2.3.1"
            )
        """
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
                decision_type.value if isinstance(decision_type, DecisionType) else decision_type,
                action_taken,
                reason,
                confidence,
                model_name,
                model_version,
                actor_type,
                actor_id,
                now,
            ),
            commit=True
        )

        if result:
            print(f"[DECISION LOGGED] {decision_id} | Type: {decision_type} | Event: {trigger_event_id}")
            return decision_id
        return None

    def log_no_action_decision(
        self,
        trigger_event_id: str,
        trigger_event_type: str,
        reason: str,
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
        return result is not None and result > 0

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
        decision_type: DecisionType,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get decisions filtered by type."""
        return self.run_query(
            """
            SELECT * FROM decision_records
            WHERE decision_type = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (decision_type.value if isinstance(decision_type, DecisionType) else decision_type, limit)
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

        with_outcome = self.run_query(
            "SELECT COUNT(*) as c FROM decision_records WHERE outcome IS NOT NULL",
            one=True
        )

        return {
            "total_decisions": total['c'] if total else 0,
            "by_type": {r['decision_type']: r['count'] for r in (by_type or [])},
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
                "confidence": float or None,
                "outcome": str or None
            }
        """
        decision = self.get_decision(decision_id)
        if not decision:
            return None

        from datetime import datetime
        when = datetime.fromtimestamp(decision['created_at']).strftime('%Y-%m-%d %H:%M:%S')

        return {
            "decision_id": decision['decision_id'],
            "when": when,
            "trigger": f"{decision['trigger_event_type']} (event: {decision['trigger_event_id']})",
            "decision": decision['decision_type'],
            "action": decision['action_taken'],
            "reason": decision['reason'],
            "confidence": decision.get('confidence'),
            "model": f"{decision.get('model_name', 'N/A')} v{decision.get('model_version', 'N/A')}" if decision.get('model_name') else None,
            "outcome": decision.get('outcome'),
        }
