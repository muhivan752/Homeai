# ===============================
# services/companion.py - Companion Mode Service (PRODUCTION)
# ===============================
# HomeAI Companion = Friend, not robot
# Default = SILENT, Offer > Push, User chooses
#
# PHILOSOPHY:
# - Silence is the default
# - Notify only when valuable
# - User ALWAYS has choice
# - Conversational, not robotic

import time
import logging
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, time as dt_time

from services.base import BaseService
from contracts.types import (
    CompanionEventType,
    NotificationMode,
    NotificationDecision,
    UserAction,
    ALWAYS_NOTIFY_EVENTS,
    NEVER_AUTO_NOTIFY_EVENTS,
    NOTIFY_WHEN_AWAY_EVENTS,
    NOTIFY_WHEN_UNUSUAL_EVENTS,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_QUIET_HOURS_END,
    DUPLICATE_SUPPRESSION_WINDOW,
)


logger = logging.getLogger("homeai.companion")


# ===============================
# MESSAGE TEMPLATES
# ===============================
# Conversational, natural language, question-based

MESSAGE_TEMPLATES = {
    # === PRESENCE ===
    CompanionEventType.UNKNOWN_PERSON: {
        "template": "Ada orang di {location} yang tidak dikenali.\nSudah ±{duration} menit.\n\nMau lihat?",
        "actions": [UserAction.VIEW, UserAction.LATER, UserAction.IGNORE],
    },
    CompanionEventType.GUEST_ARRIVED: {
        "template": "Ada tamu di {location}.\nSudah menunggu ±{duration} menit.\n\nMau lihat?",
        "actions": [UserAction.VIEW, UserAction.LATER, UserAction.IGNORE],
    },
    CompanionEventType.FAMILY_ARRIVED: {
        "template": "{person_name} sudah sampai di rumah.",
        "actions": [UserAction.ACKNOWLEDGE],
        "unusual_template": "{person_name} baru sampai rumah.\nBiasanya sudah pulang jam {expected_time}.\n\nMau hubungi?",
        "unusual_actions": [UserAction.CALL, UserAction.VIEW, UserAction.IGNORE],
    },
    CompanionEventType.CHILD_ARRIVED: {
        "template": "{person_name} sudah sampai di rumah.",
        "actions": [UserAction.ACKNOWLEDGE],
        "unusual_template": "{person_name} belum sampai rumah.\nBiasanya sudah pulang jam {expected_time}.\n\nMau cek atau hubungi?",
        "unusual_actions": [UserAction.CHECK, UserAction.CALL, UserAction.LATER],
    },

    # === DOORBELL ===
    CompanionEventType.DOORBELL_RING: {
        "template": "Ada yang membunyikan bel di {location}.\n\nMau lihat?",
        "actions": [UserAction.VIEW, UserAction.IGNORE],
    },

    # === DELIVERY ===
    CompanionEventType.COURIER_ARRIVED: {
        "template": "Kurir baru datang ke rumah.\nKamu sedang tidak di rumah.\n\nPerlu lihat snapshot?",
        "actions": [UserAction.VIEW, UserAction.LATER],
        "away_only": True,
    },
    CompanionEventType.PACKAGE_DELIVERED: {
        "template": "Paket baru saja diantar.\n\nMau lihat?",
        "actions": [UserAction.VIEW, UserAction.ACKNOWLEDGE],
    },
    CompanionEventType.PACKAGE_PICKED_UP: {
        "template": "Ada yang mengambil paket di depan rumah.\n\nMau lihat siapa?",
        "actions": [UserAction.VIEW, UserAction.IGNORE],
    },

    # === CHILD/PET ===
    CompanionEventType.CHILD_CRYING: {
        "template": "Sepertinya {person_name} menangis.\nTerdeteksi dari {location}.\n\nMau lihat?",
        "actions": [UserAction.VIEW, UserAction.IGNORE],
    },
    CompanionEventType.PET_ACTIVITY: {
        "template": "Ada aktivitas {pet_name} di {location}.\nTidak biasa untuk jam segini.\n\nMau cek?",
        "actions": [UserAction.VIEW, UserAction.IGNORE],
    },

    # === ACTIVITY ===
    CompanionEventType.MOTION_DETECTED: {
        "template": "Ada aktivitas di {location}.\nKamu sedang tidak di rumah.\n\nMau cek kamera?",
        "actions": [UserAction.VIEW, UserAction.IGNORE],
        "away_only": True,
    },
    CompanionEventType.DOOR_OPENED: {
        "template": "Pintu {location} dibuka.\nKamu sedang tidak di rumah.\n\nMau lihat?",
        "actions": [UserAction.VIEW, UserAction.IGNORE],
        "away_only": True,
    },
    CompanionEventType.UNUSUAL_ACTIVITY: {
        "template": "Ada aktivitas di {location} jam {time}.\nTidak biasa untuk jam segini.\n\nMau cek kamera?",
        "actions": [UserAction.VIEW, UserAction.IGNORE],
    },
    CompanionEventType.LOUD_NOISE: {
        "template": "Terdengar suara keras dari {location}.\n\nMau cek?",
        "actions": [UserAction.VIEW, UserAction.IGNORE],
    },

    # === ENVIRONMENTAL ===
    CompanionEventType.TEMPERATURE_ANOMALY: {
        "template": "Suhu di {location} agak {condition} ({value}°C).\nBiasanya sekitar {normal_value}°C.\n\nPerlu atur AC?",
        "actions": [UserAction.ADJUST, UserAction.IGNORE],
    },
    CompanionEventType.HUMIDITY_ANOMALY: {
        "template": "Kelembaban di {location} {condition} ({value}%).\nBisa berisiko untuk {risk}.\n\nPerlu perhatian?",
        "actions": [UserAction.ACKNOWLEDGE, UserAction.IGNORE],
    },
    CompanionEventType.AIR_QUALITY_POOR: {
        "template": "Kualitas udara di {location} kurang baik.\nDisarankan buka jendela atau nyalakan air purifier.\n\nMau atur otomatis?",
        "actions": [UserAction.ADJUST, UserAction.IGNORE],
    },

    # === SYSTEM ===
    CompanionEventType.DEVICE_OFFLINE: {
        "template": "Sensor {device_name} di {location} tidak merespons.\nMungkin perlu dicek baterainya.",
        "actions": [UserAction.ACKNOWLEDGE],
    },
    CompanionEventType.LOW_BATTERY: {
        "template": "Baterai {device_name} di {location} tinggal {value}%.\nSebaiknya diganti dalam beberapa hari.",
        "actions": [UserAction.ACKNOWLEDGE],
    },
}

# Daily digest template
DAILY_DIGEST_TEMPLATE = """Ringkasan hari ini:

{summary_items}

{closing_note}"""


@dataclass
class NotificationContext:
    """Context for notification decision."""
    user_id: int
    event_type: CompanionEventType
    location: Optional[str] = None
    person_name: Optional[str] = None
    device_name: Optional[str] = None
    duration_minutes: int = 0
    value: Optional[float] = None
    normal_value: Optional[float] = None
    expected_time: Optional[str] = None
    is_unusual: bool = False
    user_is_away: bool = False
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class NotificationResult:
    """Result of notification routing decision."""
    decision: NotificationDecision
    reason: str
    message: Optional[str] = None
    actions: List[UserAction] = None
    event_type: CompanionEventType = None
    context: NotificationContext = None


class CompanionService(BaseService):
    """
    Companion Mode Service.

    Handles notification routing and message composition for
    non-emergency events following the Companion philosophy.

    CORE PRINCIPLE: When in doubt, stay silent.
    """

    def should_notify(self, context: NotificationContext) -> NotificationResult:
        """
        Decide whether to send notification.

        This is the core decision tree implementing silence-by-default.

        Args:
            context: Full context about the event

        Returns:
            NotificationResult with decision and optional message
        """
        event_type = context.event_type

        # 1. Check if event type is NEVER auto-notify
        if event_type in NEVER_AUTO_NOTIFY_EVENTS:
            return NotificationResult(
                decision=NotificationDecision.SUPPRESS_USER_PREF,
                reason=f"Event type {event_type.value} never auto-notifies",
                event_type=event_type,
                context=context,
            )

        # 2. Check quiet hours (except ALWAYS_NOTIFY)
        if event_type not in ALWAYS_NOTIFY_EVENTS:
            if self._is_quiet_hours(context.user_id):
                return NotificationResult(
                    decision=NotificationDecision.SUPPRESS_QUIET_HOURS,
                    reason="Quiet hours active",
                    event_type=event_type,
                    context=context,
                )

        # 3. Check duplicate suppression
        if self._is_duplicate(context):
            return NotificationResult(
                decision=NotificationDecision.SUPPRESS_DUPLICATE,
                reason="Similar notification sent recently",
                event_type=event_type,
                context=context,
            )

        # 4. Check user preferences
        if not self._user_wants_notification(context.user_id, event_type):
            return NotificationResult(
                decision=NotificationDecision.SUPPRESS_USER_PREF,
                reason="User disabled this notification type",
                event_type=event_type,
                context=context,
            )

        # 5. ALWAYS_NOTIFY events → send
        if event_type in ALWAYS_NOTIFY_EVENTS:
            message, actions = self._compose_message(context)
            return NotificationResult(
                decision=NotificationDecision.SEND,
                reason=f"Event type {event_type.value} always notifies",
                message=message,
                actions=actions,
                event_type=event_type,
                context=context,
            )

        # 6. NOTIFY_WHEN_AWAY events → check if user away
        if event_type in NOTIFY_WHEN_AWAY_EVENTS:
            if context.user_is_away:
                message, actions = self._compose_message(context)
                return NotificationResult(
                    decision=NotificationDecision.SEND,
                    reason="User is away, notifying about activity",
                    message=message,
                    actions=actions,
                    event_type=event_type,
                    context=context,
                )
            else:
                return NotificationResult(
                    decision=NotificationDecision.SUPPRESS_ROUTINE,
                    reason="User is home, activity is routine",
                    event_type=event_type,
                    context=context,
                )

        # 7. NOTIFY_WHEN_UNUSUAL events → check if unusual
        if event_type in NOTIFY_WHEN_UNUSUAL_EVENTS:
            if context.is_unusual:
                message, actions = self._compose_message(context)
                return NotificationResult(
                    decision=NotificationDecision.SEND,
                    reason="Activity is unusual vs baseline",
                    message=message,
                    actions=actions,
                    event_type=event_type,
                    context=context,
                )
            else:
                return NotificationResult(
                    decision=NotificationDecision.SUPPRESS_BASELINE,
                    reason="Activity matches normal baseline",
                    event_type=event_type,
                    context=context,
                )

        # 8. Default: suppress (silence is the default)
        return NotificationResult(
            decision=NotificationDecision.SUPPRESS_ROUTINE,
            reason="Default: silence unless explicitly needed",
            event_type=event_type,
            context=context,
        )

    def _compose_message(self, context: NotificationContext) -> Tuple[str, List[UserAction]]:
        """
        Compose notification message from template.

        Returns:
            Tuple of (message, actions)
        """
        template_info = MESSAGE_TEMPLATES.get(context.event_type)
        if not template_info:
            # Fallback generic message
            return (
                f"Ada aktivitas di {context.location or 'rumah'}.\n\nMau cek?",
                [UserAction.VIEW, UserAction.IGNORE]
            )

        # Choose template based on context
        if context.is_unusual and "unusual_template" in template_info:
            template = template_info["unusual_template"]
            actions = template_info.get("unusual_actions", template_info["actions"])
        else:
            template = template_info["template"]
            actions = template_info["actions"]

        # Format template with context
        now = datetime.now()
        format_vars = {
            "location": context.location or "rumah",
            "person_name": context.person_name or "Seseorang",
            "device_name": context.device_name or "perangkat",
            "duration": context.duration_minutes,
            "value": context.value,
            "normal_value": context.normal_value,
            "expected_time": context.expected_time or "biasanya",
            "time": now.strftime("%H:%M"),
            "condition": self._get_condition_word(context),
            "risk": self._get_risk_description(context),
            "pet_name": context.metadata.get("pet_name", "hewan peliharaan"),
        }

        try:
            message = template.format(**format_vars)
        except KeyError:
            # Fallback if template vars missing
            message = template

        return message, actions

    def _get_condition_word(self, context: NotificationContext) -> str:
        """Get condition word for temperature/humidity."""
        if context.value is None or context.normal_value is None:
            return "tidak normal"

        if context.event_type == CompanionEventType.TEMPERATURE_ANOMALY:
            return "panas" if context.value > context.normal_value else "dingin"
        elif context.event_type == CompanionEventType.HUMIDITY_ANOMALY:
            return "tinggi" if context.value > context.normal_value else "rendah"
        return "tidak normal"

    def _get_risk_description(self, context: NotificationContext) -> str:
        """Get risk description for environmental anomalies."""
        if context.event_type == CompanionEventType.HUMIDITY_ANOMALY:
            if context.value and context.value > 70:
                return "jamur dan kerusakan furnitur"
            elif context.value and context.value < 30:
                return "kulit kering dan iritasi"
        return "kenyamanan"

    def _is_quiet_hours(self, user_id: int) -> bool:
        """Check if current time is in quiet hours for user."""
        prefs = self._get_user_preferences(user_id)
        if not prefs or not prefs.get("quiet_hours_enabled", True):
            return False

        start_str = prefs.get("quiet_hours_start", DEFAULT_QUIET_HOURS_START)
        end_str = prefs.get("quiet_hours_end", DEFAULT_QUIET_HOURS_END)

        try:
            start = datetime.strptime(start_str, "%H:%M").time()
            end = datetime.strptime(end_str, "%H:%M").time()
            now = datetime.now().time()

            # Handle overnight quiet hours (e.g., 23:00 - 07:00)
            if start > end:
                return now >= start or now <= end
            else:
                return start <= now <= end
        except ValueError:
            return False

    def _is_duplicate(self, context: NotificationContext) -> bool:
        """Check if similar notification was sent recently."""
        result = self.run_query(
            """
            SELECT COUNT(*) as c FROM notification_log
            WHERE user_id = ? AND event_type = ? AND location = ?
            AND created_at > ?
            """,
            (
                context.user_id,
                context.event_type.value,
                context.location,
                int(time.time()) - DUPLICATE_SUPPRESSION_WINDOW
            ),
            one=True
        )
        return result and result["c"] > 0

    def _user_wants_notification(self, user_id: int, event_type: CompanionEventType) -> bool:
        """Check user preferences for this event type."""
        prefs = self._get_user_preferences(user_id)
        if not prefs:
            return True  # Default to notify if no prefs set

        event_prefs = prefs.get("events", {})
        return event_prefs.get(event_type.value, True)

    def _get_user_preferences(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user notification preferences."""
        result = self.run_query(
            "SELECT preferences FROM notification_preferences WHERE user_id = ?",
            (user_id,),
            one=True
        )
        if result and result.get("preferences"):
            import json
            try:
                return json.loads(result["preferences"])
            except json.JSONDecodeError:
                return None
        return None

    def log_notification(
        self,
        context: NotificationContext,
        result: NotificationResult
    ) -> Optional[int]:
        """Log notification decision for learning and audit."""
        now = int(time.time())

        return self.run_query(
            """
            INSERT INTO notification_log (
                user_id, event_type, location, decision, reason,
                message_sent, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                context.user_id,
                context.event_type.value,
                context.location,
                result.decision.value,
                result.reason,
                result.message is not None,
                now
            ),
            commit=True
        )

    def set_user_preferences(
        self,
        user_id: int,
        mode: NotificationMode = NotificationMode.BALANCED,
        event_settings: Dict[str, bool] = None,
        quiet_hours_enabled: bool = True,
        quiet_hours_start: str = DEFAULT_QUIET_HOURS_START,
        quiet_hours_end: str = DEFAULT_QUIET_HOURS_END,
        daily_digest_enabled: bool = False,
        daily_digest_time: str = "21:00",
    ) -> bool:
        """Set user notification preferences."""
        import json

        prefs = {
            "mode": mode.value,
            "events": event_settings or {},
            "quiet_hours_enabled": quiet_hours_enabled,
            "quiet_hours_start": quiet_hours_start,
            "quiet_hours_end": quiet_hours_end,
            "daily_digest_enabled": daily_digest_enabled,
            "daily_digest_time": daily_digest_time,
        }

        now = int(time.time())
        prefs_json = json.dumps(prefs)

        # Upsert
        existing = self.run_query(
            "SELECT id FROM notification_preferences WHERE user_id = ?",
            (user_id,),
            one=True
        )

        if existing:
            result = self.run_query(
                """
                UPDATE notification_preferences
                SET preferences = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (prefs_json, now, user_id),
                commit=True
            )
        else:
            result = self.run_query(
                """
                INSERT INTO notification_preferences (user_id, preferences, created_at)
                VALUES (?, ?, ?)
                """,
                (user_id, prefs_json, now),
                commit=True
            )

        return result is not None

    def compose_daily_digest(self, user_id: int) -> Optional[str]:
        """
        Compose daily digest message.

        Only called if user has opted in.
        """
        # Get today's activity summary
        today_start = int(datetime.now().replace(hour=0, minute=0, second=0).timestamp())

        events = self.run_query(
            """
            SELECT event_type, location, COUNT(*) as count,
                   MIN(created_at) as first_at, MAX(created_at) as last_at
            FROM notification_log
            WHERE user_id = ? AND created_at >= ?
            GROUP BY event_type, location
            ORDER BY count DESC
            LIMIT 10
            """,
            (user_id, today_start)
        )

        if not events:
            return None

        # Build summary items
        items = []
        for event in events:
            event_type = event["event_type"]
            location = event["location"] or "rumah"
            first_time = datetime.fromtimestamp(event["first_at"]).strftime("%H:%M")

            # Format naturally
            if event_type == "courier_arrived":
                items.append(f"• Kurir datang {self._time_to_natural(first_time)}")
            elif event_type == "child_arrived":
                items.append(f"• Anak pulang jam {first_time}")
            elif event_type == "family_arrived":
                items.append(f"• Ada yang pulang jam {first_time}")
            elif event_type == "motion_detected" and event["count"] > 1:
                items.append(f"• Aktivitas di {location} ({event['count']}x)")

        if not items:
            return None

        summary_items = "\n".join(items[:5])  # Max 5 items

        # Closing note based on activity level
        if len(events) <= 2:
            closing_note = "Hari yang tenang."
        else:
            closing_note = "Tidak ada yang perlu perhatian khusus."

        return DAILY_DIGEST_TEMPLATE.format(
            summary_items=summary_items,
            closing_note=closing_note
        )

    def _time_to_natural(self, time_str: str) -> str:
        """Convert time to natural language."""
        hour = int(time_str.split(":")[0])
        if 5 <= hour < 12:
            return "pagi"
        elif 12 <= hour < 15:
            return "siang"
        elif 15 <= hour < 18:
            return "sore"
        else:
            return "malam"

    def get_notification_stats(self, user_id: int, days: int = 7) -> Dict[str, Any]:
        """Get notification statistics for user."""
        since = int(time.time()) - (days * 24 * 60 * 60)

        total = self.run_query(
            "SELECT COUNT(*) as c FROM notification_log WHERE user_id = ? AND created_at >= ?",
            (user_id, since),
            one=True
        )

        by_decision = self.run_query(
            """
            SELECT decision, COUNT(*) as count
            FROM notification_log
            WHERE user_id = ? AND created_at >= ?
            GROUP BY decision
            """,
            (user_id, since)
        )

        sent_count = 0
        suppressed_count = 0
        for row in (by_decision or []):
            if row["decision"] == "send":
                sent_count = row["count"]
            else:
                suppressed_count += row["count"]

        return {
            "total_events": total["c"] if total else 0,
            "notifications_sent": sent_count,
            "notifications_suppressed": suppressed_count,
            "silence_rate": suppressed_count / max(total["c"], 1) if total else 0,
            "by_decision": {r["decision"]: r["count"] for r in (by_decision or [])},
        }
