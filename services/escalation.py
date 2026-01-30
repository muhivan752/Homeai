# ===============================
# services/escalation.py - Escalation Engine (PRODUCTION)
# ===============================
# CORE PHILOSOPHY:
# - Assistive-first, policy-driven autonomy
# - NO silent escalation
# - NO auto-call authority without explicit consent
# - 30 second confirmation window (non-negotiable)
# - Violence detection: alert trusted humans, don't stay silent
#
# This engine answers: "What should system do when emergency X happens?"

import time
import logging
import threading
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass
from enum import Enum

from services.base import BaseService
from contracts.types import (
    EmergencyType,
    EscalationAction,
    ConfirmationStatus,
    ConsentType,
    DecisionType,
    ActorType,
    DEFAULT_CONFIRMATION_WINDOW,
    DEFAULT_AUTO_ESCALATE_CONFIDENCE,
    DEFAULT_ESCALATION_ACTIONS,
    CONFIDENCE_THRESHOLDS,
)


logger = logging.getLogger("homeai.escalation")


@dataclass
class EscalationContext:
    """
    Context for an escalation decision.

    Contains all information needed to decide what actions to take.
    """
    user_id: int
    event_id: str
    event_type: str
    emergency_type: EmergencyType
    confidence: float
    location: Optional[str] = None
    device_id: Optional[int] = None

    # Additional context
    multiple_sensors: bool = False
    duration_seconds: float = 0
    corroborating_events: List[str] = None


@dataclass
class EscalationDecision:
    """
    Result of escalation decision.

    Explains WHAT to do and WHY (for audit trail).
    """
    event_id: str
    emergency_type: EmergencyType
    confidence: float

    # Actions to take
    immediate_actions: List[EscalationAction]
    deferred_actions: List[EscalationAction]  # After confirmation
    blocked_actions: List[EscalationAction]   # Requires consent not given

    # Confirmation
    requires_confirmation: bool
    confirmation_window_seconds: int

    # Reasoning (for DecisionService)
    reason: str
    confidence_tier: str  # "low", "medium", "high", "very_high"


class EscalationEngine(BaseService):
    """
    Core Escalation Decision Engine.

    ARCHITECTURE:

    ┌─────────────────────────────────────────────────────────────────┐
    │                    ESCALATION FLOW                              │
    │                                                                 │
    │   Event → Classify → Check Policy → Check Consent → Decide     │
    │                                                                 │
    │   1. What type of emergency?                                    │
    │   2. What's the confidence level?                               │
    │   3. What has user consented to?                               │
    │   4. What actions are allowed by policy?                        │
    │   5. Does this require confirmation?                            │
    │   6. Execute allowed actions, defer others                      │
    └─────────────────────────────────────────────────────────────────┘

    RULES (NON-NEGOTIABLE):
    1. NEVER auto-call authority without explicit consent
    2. NEVER silent recording
    3. NEVER shorten confirmation window below 30 seconds
    4. ALWAYS alert owner (unless explicitly disabled)
    5. Violence detection: ALWAYS alert at least trusted contacts
    """

    def __init__(self, db_path: str):
        super().__init__(db_path)
        self._policy_cache: Dict[int, Dict[str, Any]] = {}
        self._consent_cache: Dict[int, Set[str]] = {}
        self._cache_lock = threading.Lock()

    def decide(self, context: EscalationContext) -> EscalationDecision:
        """
        Main decision method.

        Takes escalation context and returns decision with actions.

        Args:
            context: EscalationContext with all event information

        Returns:
            EscalationDecision with actions and reasoning
        """
        logger.info(
            "Escalation decision for %s | Type: %s | Confidence: %.2f",
            context.event_id, context.emergency_type.value, context.confidence
        )

        # 1. Get user's policy for this emergency type
        policy = self._get_policy(context.user_id, context.emergency_type)

        # 2. Get user's consents
        consents = self._get_consents(context.user_id)

        # 3. Determine confidence tier
        confidence_tier = self._get_confidence_tier(context.confidence)

        # 4. Get default actions for this emergency type
        default_actions = DEFAULT_ESCALATION_ACTIONS.get(
            context.emergency_type,
            DEFAULT_ESCALATION_ACTIONS[EmergencyType.INTRUSION]
        )

        # 5. Determine actions based on confidence and consent
        immediate_actions = []
        deferred_actions = []
        blocked_actions = []

        # Process immediate actions
        for action in default_actions["immediate"]:
            if self._is_action_allowed(action, policy, consents):
                immediate_actions.append(action)
            else:
                blocked_actions.append(action)

        # Process actions that require confirmation
        for action in default_actions["after_confirmation"]:
            if self._is_action_allowed(action, policy, consents):
                deferred_actions.append(action)
            else:
                blocked_actions.append(action)

        # Process consent-required actions
        for action in default_actions["requires_consent"]:
            if self._is_action_allowed(action, policy, consents):
                # Only add if confidence is high enough
                if confidence_tier in ["high", "very_high"]:
                    deferred_actions.append(action)
            else:
                blocked_actions.append(action)

        # 6. Special handling for high confidence
        if confidence_tier == "very_high" and context.multiple_sensors:
            # Move some deferred actions to immediate
            # But NEVER move authority calls without confirmation
            safe_to_immediate = [
                EscalationAction.ALERT_TRUSTED,
                EscalationAction.ALERT_FAMILY,
                EscalationAction.LOCAL_ALARM,
            ]
            for action in list(deferred_actions):
                if action in safe_to_immediate:
                    deferred_actions.remove(action)
                    if action not in immediate_actions:
                        immediate_actions.append(action)

        # 7. Determine if confirmation is required
        requires_confirmation = policy.get("confirmation_required", True)
        confirmation_window = policy.get(
            "confirmation_window_seconds",
            DEFAULT_CONFIRMATION_WINDOW
        )

        # CRITICAL: Never go below 30 seconds
        if confirmation_window < DEFAULT_CONFIRMATION_WINDOW:
            logger.warning(
                "Policy tried to set window to %ds, enforcing minimum %ds",
                confirmation_window, DEFAULT_CONFIRMATION_WINDOW
            )
            confirmation_window = DEFAULT_CONFIRMATION_WINDOW

        # 8. Build reasoning
        reason = self._build_reason(
            context, confidence_tier, immediate_actions,
            deferred_actions, blocked_actions, consents
        )

        decision = EscalationDecision(
            event_id=context.event_id,
            emergency_type=context.emergency_type,
            confidence=context.confidence,
            immediate_actions=immediate_actions,
            deferred_actions=deferred_actions,
            blocked_actions=blocked_actions,
            requires_confirmation=requires_confirmation,
            confirmation_window_seconds=confirmation_window,
            reason=reason,
            confidence_tier=confidence_tier,
        )

        logger.info(
            "Decision: Immediate=%s | Deferred=%s | Blocked=%s | Confirm=%s",
            [a.value for a in immediate_actions],
            [a.value for a in deferred_actions],
            [a.value for a in blocked_actions],
            requires_confirmation
        )

        return decision

    def _get_policy(self, user_id: int, emergency_type: EmergencyType) -> Dict[str, Any]:
        """Get user's escalation policy for emergency type."""
        with self._cache_lock:
            cache_key = f"{user_id}_{emergency_type.value}"
            if cache_key in self._policy_cache:
                return self._policy_cache[cache_key]

        policy = self.run_query(
            """
            SELECT * FROM escalation_policies
            WHERE user_id = ? AND event_type = ? AND is_active = 1
            """,
            (user_id, emergency_type.value),
            one=True
        )

        if policy:
            result = dict(policy)
        else:
            # Return conservative defaults
            result = {
                "confirmation_required": True,
                "confirmation_window_seconds": DEFAULT_CONFIRMATION_WINDOW,
                "auto_escalate_confidence": DEFAULT_AUTO_ESCALATE_CONFIDENCE,
                "allow_local_alarm": True,
                "allow_alert_owner": True,
                "allow_alert_family": True,
                "allow_alert_trusted": True,
                "allow_call_authority": False,  # CONSERVATIVE DEFAULT
                "allow_recording": False,       # CONSERVATIVE DEFAULT
            }

        with self._cache_lock:
            self._policy_cache[cache_key] = result

        return result

    def _get_consents(self, user_id: int) -> Set[str]:
        """Get user's granted consents."""
        with self._cache_lock:
            if user_id in self._consent_cache:
                return self._consent_cache[user_id]

        consents = self.run_query(
            """
            SELECT consent_type FROM user_consents
            WHERE user_id = ? AND granted = 1 AND revoked_at IS NULL
            """,
            (user_id,)
        )

        result = {c["consent_type"] for c in (consents or [])}

        with self._cache_lock:
            self._consent_cache[user_id] = result

        return result

    def _get_confidence_tier(self, confidence: float) -> str:
        """Determine confidence tier based on thresholds."""
        if confidence >= CONFIDENCE_THRESHOLDS["very_high"]:
            return "very_high"
        elif confidence >= CONFIDENCE_THRESHOLDS["high"]:
            return "high"
        elif confidence >= CONFIDENCE_THRESHOLDS["medium"]:
            return "medium"
        else:
            return "low"

    def _is_action_allowed(
        self,
        action: EscalationAction,
        policy: Dict[str, Any],
        consents: Set[str]
    ) -> bool:
        """Check if action is allowed by policy and consent."""

        # Map actions to policy keys and consent requirements
        action_requirements = {
            EscalationAction.LOCAL_ALARM: {
                "policy_key": "allow_local_alarm",
                "consent_required": None,
            },
            EscalationAction.ALERT_OWNER: {
                "policy_key": "allow_alert_owner",
                "consent_required": None,
            },
            EscalationAction.ALERT_FAMILY: {
                "policy_key": "allow_alert_family",
                "consent_required": None,
            },
            EscalationAction.ALERT_TRUSTED: {
                "policy_key": "allow_alert_trusted",
                "consent_required": ConsentType.TRUSTED_CONTACT_ALERT.value,
            },
            EscalationAction.CALL_POLICE: {
                "policy_key": "allow_call_authority",
                "consent_required": ConsentType.AUTHORITY_ESCALATION.value,
            },
            EscalationAction.CALL_FIRE: {
                "policy_key": "allow_call_authority",
                "consent_required": ConsentType.AUTHORITY_ESCALATION.value,
            },
            EscalationAction.CALL_AMBULANCE: {
                "policy_key": "allow_call_authority",
                "consent_required": ConsentType.AUTHORITY_ESCALATION.value,
            },
            EscalationAction.RECORD_EVIDENCE: {
                "policy_key": "allow_recording",
                "consent_required": ConsentType.EMERGENCY_RECORDING.value,
            },
            EscalationAction.LOCKDOWN: {
                "policy_key": "allow_local_alarm",  # Treated as local action
                "consent_required": None,
            },
            EscalationAction.DISABLE_DEVICE: {
                "policy_key": "allow_local_alarm",  # Treated as local action
                "consent_required": None,
            },
        }

        req = action_requirements.get(action)
        if not req:
            return False

        # Check policy
        policy_key = req["policy_key"]
        if policy_key and not policy.get(policy_key, False):
            return False

        # Check consent
        consent_required = req["consent_required"]
        if consent_required and consent_required not in consents:
            return False

        return True

    def _build_reason(
        self,
        context: EscalationContext,
        confidence_tier: str,
        immediate: List[EscalationAction],
        deferred: List[EscalationAction],
        blocked: List[EscalationAction],
        consents: Set[str]
    ) -> str:
        """Build human-readable reason for decision."""
        parts = []

        # Describe the trigger
        parts.append(
            f"{context.emergency_type.value.replace('_', ' ').title()} detected "
            f"with {confidence_tier} confidence ({context.confidence:.0%})"
        )

        if context.location:
            parts.append(f"at {context.location}")

        if context.multiple_sensors:
            parts.append("confirmed by multiple sensors")

        # Describe actions
        if immediate:
            parts.append(
                f"Immediate actions: {', '.join(a.value for a in immediate)}"
            )

        if deferred:
            parts.append(
                f"Pending confirmation: {', '.join(a.value for a in deferred)}"
            )

        if blocked:
            missing_consents = []
            if ConsentType.AUTHORITY_ESCALATION.value not in consents:
                if any(a in blocked for a in [
                    EscalationAction.CALL_POLICE,
                    EscalationAction.CALL_FIRE,
                    EscalationAction.CALL_AMBULANCE
                ]):
                    missing_consents.append("authority escalation")
            if ConsentType.EMERGENCY_RECORDING.value not in consents:
                if EscalationAction.RECORD_EVIDENCE in blocked:
                    missing_consents.append("emergency recording")

            if missing_consents:
                parts.append(
                    f"Blocked due to missing consent: {', '.join(missing_consents)}"
                )

        return ". ".join(parts) + "."

    def invalidate_cache(self, user_id: int = None):
        """Invalidate policy/consent cache."""
        with self._cache_lock:
            if user_id:
                # Invalidate specific user
                keys_to_remove = [
                    k for k in self._policy_cache.keys()
                    if k.startswith(f"{user_id}_")
                ]
                for k in keys_to_remove:
                    del self._policy_cache[k]
                self._consent_cache.pop(user_id, None)
            else:
                # Invalidate all
                self._policy_cache.clear()
                self._consent_cache.clear()

    # ===============================
    # POLICY MANAGEMENT
    # ===============================

    def set_policy(
        self,
        user_id: int,
        emergency_type: EmergencyType,
        confirmation_required: bool = True,
        confirmation_window_seconds: int = DEFAULT_CONFIRMATION_WINDOW,
        allow_local_alarm: bool = True,
        allow_alert_owner: bool = True,
        allow_alert_family: bool = True,
        allow_alert_trusted: bool = True,
        allow_call_authority: bool = False,
        allow_recording: bool = False,
    ) -> bool:
        """
        Set escalation policy for user.

        IMPORTANT: This should only be called through proper UI flow
        that ensures user understands implications.
        """
        # Enforce minimum confirmation window
        if confirmation_window_seconds < DEFAULT_CONFIRMATION_WINDOW:
            logger.warning(
                "Attempted to set window below minimum. Enforcing %ds",
                DEFAULT_CONFIRMATION_WINDOW
            )
            confirmation_window_seconds = DEFAULT_CONFIRMATION_WINDOW

        now = int(time.time())

        result = self.run_query(
            """
            INSERT INTO escalation_policies (
                user_id, event_type, confirmation_required, confirmation_window_seconds,
                allow_local_alarm, allow_alert_owner, allow_alert_family,
                allow_alert_trusted, allow_call_authority, allow_recording,
                is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(user_id, event_type) DO UPDATE SET
                confirmation_required = excluded.confirmation_required,
                confirmation_window_seconds = excluded.confirmation_window_seconds,
                allow_local_alarm = excluded.allow_local_alarm,
                allow_alert_owner = excluded.allow_alert_owner,
                allow_alert_family = excluded.allow_alert_family,
                allow_alert_trusted = excluded.allow_alert_trusted,
                allow_call_authority = excluded.allow_call_authority,
                allow_recording = excluded.allow_recording,
                updated_at = excluded.updated_at
            """,
            (
                user_id, emergency_type.value, confirmation_required,
                confirmation_window_seconds, allow_local_alarm, allow_alert_owner,
                allow_alert_family, allow_alert_trusted, allow_call_authority,
                allow_recording, now, now
            ),
            commit=True
        )

        self.invalidate_cache(user_id)

        logger.info(
            "Policy updated for user %d | Type: %s | Authority: %s | Recording: %s",
            user_id, emergency_type.value, allow_call_authority, allow_recording
        )

        return result is not None

    def get_user_policies(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all policies for a user."""
        return self.run_query(
            "SELECT * FROM escalation_policies WHERE user_id = ? AND is_active = 1",
            (user_id,)
        ) or []

    # ===============================
    # CONSENT MANAGEMENT
    # ===============================

    def grant_consent(
        self,
        user_id: int,
        consent_type: ConsentType,
        consent_version: str,
        consent_text_hash: str,
        consent_method: str = "checkbox",
        ip_address: str = None,
        user_agent: str = None,
    ) -> bool:
        """
        Record user granting consent.

        IMPORTANT: This should ONLY be called after user has:
        1. Read the consent text
        2. Actively checked/signed/confirmed
        3. Understood what they're consenting to
        """
        now = int(time.time())

        result = self.run_query(
            """
            INSERT INTO user_consents (
                user_id, consent_type, granted, granted_at,
                consent_version, consent_text_hash, consent_method,
                ip_address, user_agent, created_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, consent_type) DO UPDATE SET
                granted = 1,
                granted_at = excluded.granted_at,
                revoked_at = NULL,
                consent_version = excluded.consent_version,
                consent_text_hash = excluded.consent_text_hash,
                consent_method = excluded.consent_method,
                ip_address = excluded.ip_address,
                user_agent = excluded.user_agent
            """,
            (
                user_id, consent_type.value, now,
                consent_version, consent_text_hash, consent_method,
                ip_address, user_agent, now
            ),
            commit=True
        )

        self.invalidate_cache(user_id)

        logger.info(
            "Consent granted: user %d | type: %s | method: %s",
            user_id, consent_type.value, consent_method
        )

        return result is not None

    def revoke_consent(self, user_id: int, consent_type: ConsentType) -> bool:
        """Revoke a previously granted consent."""
        now = int(time.time())

        result = self.run_query(
            """
            UPDATE user_consents
            SET granted = 0, revoked_at = ?
            WHERE user_id = ? AND consent_type = ?
            """,
            (now, user_id, consent_type.value),
            commit=True
        )

        self.invalidate_cache(user_id)

        logger.info("Consent revoked: user %d | type: %s", user_id, consent_type.value)

        return result is not None and result > 0

    def get_user_consents(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all consents for a user."""
        return self.run_query(
            "SELECT * FROM user_consents WHERE user_id = ?",
            (user_id,)
        ) or []

    def has_consent(self, user_id: int, consent_type: ConsentType) -> bool:
        """Check if user has specific consent."""
        consents = self._get_consents(user_id)
        return consent_type.value in consents
