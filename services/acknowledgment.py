# ===============================
# services/acknowledgment.py - Active Acknowledgment Service (PRODUCTION)
# ===============================
# Handles active user acknowledgment of system limitations.
#
# CRITICAL PHILOSOPHY:
# - NOT a passive ToS checkbox
# - User MUST actively acknowledge each limitation
# - System cannot be used until all acknowledged
# - This is for user protection AND liability

import time
import hashlib
import logging
from typing import Optional, List, Dict, Any

from services.base import BaseService


logger = logging.getLogger("homeai.acknowledgment")


# ===============================
# ACKNOWLEDGMENT TEXTS (Version 1.0)
# ===============================
# These are the exact texts users must acknowledge.
# Version number changes when text changes significantly.
# Hash is computed to verify user saw the exact text.

ACKNOWLEDGMENT_VERSION = "1.0"

ACKNOWLEDGMENT_TEXTS = {
    "system_not_replacement": {
        "title": "HomeAI is NOT a Replacement for Professional Security",
        "text": (
            "I understand that HomeAI is an assistive system and NOT a replacement for:\n"
            "• Professional security monitoring services\n"
            "• Emergency services (police, fire, ambulance)\n"
            "• Home insurance\n"
            "• Physical security measures (locks, alarms, etc.)\n\n"
            "HomeAI is designed to ASSIST, not replace, these essential services."
        ),
        "db_field": "ack_system_not_replacement",
    },
    "internet_dependency": {
        "title": "Internet Connection Required",
        "text": (
            "I understand that HomeAI requires internet connection to function fully.\n\n"
            "If internet is unavailable:\n"
            "• Cloud notifications will not be sent\n"
            "• Remote access will not work\n"
            "• Some features may be limited\n\n"
            "Edge devices can operate locally during outages, but communication "
            "with the cloud will be interrupted."
        ),
        "db_field": "ack_internet_dependency",
    },
    "false_positive_possible": {
        "title": "False Positives and Negatives May Occur",
        "text": (
            "I understand that AI-based detection is not perfect.\n\n"
            "• FALSE POSITIVES: The system may incorrectly report threats that don't exist\n"
            "• FALSE NEGATIVES: The system may fail to detect real threats\n\n"
            "No AI system can guarantee 100% accuracy. I will use my own judgment "
            "and not rely solely on HomeAI for security decisions."
        ),
        "db_field": "ack_false_positive_possible",
    },
    "evidence_not_court_proof": {
        "title": "Evidence May Not Be Court-Admissible",
        "text": (
            "I understand that recordings and evidence collected by HomeAI:\n\n"
            "• May not be admissible in court in all jurisdictions\n"
            "• Should not be relied upon as sole evidence\n"
            "• May have legal restrictions on use\n"
            "• May be subject to local privacy laws\n\n"
            "I will consult legal counsel before using HomeAI evidence in legal proceedings."
        ),
        "db_field": "ack_evidence_not_court_proof",
    },
    "response_time_not_guaranteed": {
        "title": "Response Time Cannot Be Guaranteed",
        "text": (
            "I understand that HomeAI cannot guarantee response times.\n\n"
            "Factors that may delay response:\n"
            "• Network latency and connectivity issues\n"
            "• Server load and availability\n"
            "• Third-party service delays (SMS, calls)\n"
            "• Hardware malfunctions\n\n"
            "In life-threatening emergencies, I will ALWAYS call emergency services "
            "directly rather than relying solely on HomeAI."
        ),
        "db_field": "ack_response_time_not_guaranteed",
    },
}


def compute_text_hash(text: str) -> str:
    """Compute SHA-256 hash of acknowledgment text."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


class AcknowledgmentService(BaseService):
    """
    Active Acknowledgment Service.

    Manages the onboarding flow where users must actively acknowledge
    system limitations before using critical features.

    FLOW:
    1. New user registers
    2. Before accessing emergency features, must complete acknowledgments
    3. Each acknowledgment is presented individually
    4. User must check box AND confirm they understand
    5. All acknowledgments stored with timestamp and version
    6. Features unlock only after all acknowledged

    WHY THIS EXISTS:
    - User protection: Ensure they understand what system can/can't do
    - Liability: Document that user was informed of limitations
    - Trust: Transparent about capabilities and limitations
    - Legal: May be required for some jurisdictions/use cases
    """

    def get_acknowledgment_status(self, user_id: int) -> Dict[str, Any]:
        """
        Get current acknowledgment status for user.

        Returns:
            {
                "all_acknowledged": bool,
                "acknowledged_at": timestamp or None,
                "version": str,
                "items": {
                    "system_not_replacement": {"acknowledged": bool, "title": str},
                    ...
                }
            }
        """
        ack = self.run_query(
            "SELECT * FROM user_acknowledgments WHERE user_id = ?",
            (user_id,),
            one=True
        )

        items = {}
        for key, info in ACKNOWLEDGMENT_TEXTS.items():
            if ack:
                acknowledged = bool(ack.get(info["db_field"], 0))
            else:
                acknowledged = False

            items[key] = {
                "acknowledged": acknowledged,
                "title": info["title"],
                "text_hash": compute_text_hash(info["text"]),
            }

        return {
            "all_acknowledged": ack["all_acknowledged"] if ack else False,
            "acknowledged_at": ack["acknowledged_at"] if ack else None,
            "version": ack["acknowledgment_version"] if ack else None,
            "current_version": ACKNOWLEDGMENT_VERSION,
            "items": items,
        }

    def get_acknowledgment_text(self, key: str) -> Optional[Dict[str, str]]:
        """
        Get the text for a specific acknowledgment.

        Args:
            key: Acknowledgment key (e.g., "system_not_replacement")

        Returns:
            {"title": str, "text": str, "hash": str} or None
        """
        info = ACKNOWLEDGMENT_TEXTS.get(key)
        if not info:
            return None

        return {
            "title": info["title"],
            "text": info["text"],
            "hash": compute_text_hash(info["text"]),
        }

    def get_all_acknowledgment_texts(self) -> List[Dict[str, Any]]:
        """Get all acknowledgment texts in order."""
        return [
            {
                "key": key,
                "title": info["title"],
                "text": info["text"],
                "hash": compute_text_hash(info["text"]),
            }
            for key, info in ACKNOWLEDGMENT_TEXTS.items()
        ]

    def acknowledge_item(
        self,
        user_id: int,
        key: str,
        confirmed_hash: str,
    ) -> bool:
        """
        Acknowledge a single item.

        Args:
            user_id: User acknowledging
            key: Which acknowledgment (e.g., "system_not_replacement")
            confirmed_hash: Hash of text user saw (must match current)

        Returns:
            True if acknowledged successfully

        Raises:
            ValueError: If key invalid or hash mismatch
        """
        info = ACKNOWLEDGMENT_TEXTS.get(key)
        if not info:
            raise ValueError(f"Invalid acknowledgment key: {key}")

        # Verify hash matches (user saw correct text)
        expected_hash = compute_text_hash(info["text"])
        if confirmed_hash != expected_hash:
            raise ValueError(
                f"Text hash mismatch. User may have seen outdated text. "
                f"Expected: {expected_hash}, Got: {confirmed_hash}"
            )

        now = int(time.time())
        db_field = info["db_field"]

        # Check if record exists
        existing = self.run_query(
            "SELECT id FROM user_acknowledgments WHERE user_id = ?",
            (user_id,),
            one=True
        )

        if existing:
            # Update existing record
            self.run_query(
                f"""
                UPDATE user_acknowledgments
                SET {db_field} = 1, acknowledgment_version = ?
                WHERE user_id = ?
                """,
                (ACKNOWLEDGMENT_VERSION, user_id),
                commit=True
            )
        else:
            # Create new record
            self.run_query(
                f"""
                INSERT INTO user_acknowledgments (
                    user_id, {db_field}, acknowledgment_version, created_at
                ) VALUES (?, 1, ?, ?)
                """,
                (user_id, ACKNOWLEDGMENT_VERSION, now),
                commit=True
            )

        logger.info(
            "Acknowledgment recorded: user %d | item: %s",
            user_id, key
        )

        # Check if all acknowledged now
        self._check_all_acknowledged(user_id)

        return True

    def _check_all_acknowledged(self, user_id: int):
        """Check if all items are acknowledged and update status."""
        ack = self.run_query(
            "SELECT * FROM user_acknowledgments WHERE user_id = ?",
            (user_id,),
            one=True
        )

        if not ack:
            return

        # Check each field
        all_done = all(
            ack.get(info["db_field"], 0)
            for info in ACKNOWLEDGMENT_TEXTS.values()
        )

        if all_done and not ack["all_acknowledged"]:
            now = int(time.time())
            self.run_query(
                """
                UPDATE user_acknowledgments
                SET all_acknowledged = 1, acknowledged_at = ?
                WHERE user_id = ?
                """,
                (now, user_id),
                commit=True
            )
            logger.info("All acknowledgments complete: user %d", user_id)

    def is_fully_acknowledged(self, user_id: int) -> bool:
        """Check if user has acknowledged all items."""
        ack = self.run_query(
            "SELECT all_acknowledged FROM user_acknowledgments WHERE user_id = ?",
            (user_id,),
            one=True
        )
        return bool(ack and ack["all_acknowledged"])

    def requires_reacknowledgment(self, user_id: int) -> bool:
        """
        Check if user needs to re-acknowledge due to version change.

        When acknowledgment text changes significantly, users must re-acknowledge.
        """
        ack = self.run_query(
            "SELECT acknowledgment_version FROM user_acknowledgments WHERE user_id = ?",
            (user_id,),
            one=True
        )

        if not ack:
            return True

        # If version is different, need to re-acknowledge
        return ack["acknowledgment_version"] != ACKNOWLEDGMENT_VERSION

    def get_pending_acknowledgments(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Get list of acknowledgments user still needs to complete.

        Returns:
            List of {"key": str, "title": str, "text": str}
        """
        ack = self.run_query(
            "SELECT * FROM user_acknowledgments WHERE user_id = ?",
            (user_id,),
            one=True
        )

        pending = []
        for key, info in ACKNOWLEDGMENT_TEXTS.items():
            if not ack or not ack.get(info["db_field"], 0):
                pending.append({
                    "key": key,
                    "title": info["title"],
                    "text": info["text"],
                    "hash": compute_text_hash(info["text"]),
                })

        return pending

    def reset_acknowledgments(self, user_id: int) -> bool:
        """
        Reset all acknowledgments for a user.

        Use when acknowledgment version changes or for testing.
        """
        result = self.run_query(
            """
            UPDATE user_acknowledgments
            SET ack_system_not_replacement = 0,
                ack_internet_dependency = 0,
                ack_false_positive_possible = 0,
                ack_evidence_not_court_proof = 0,
                ack_response_time_not_guaranteed = 0,
                all_acknowledged = 0,
                acknowledged_at = NULL
            WHERE user_id = ?
            """,
            (user_id,),
            commit=True
        )

        if result:
            logger.info("Acknowledgments reset: user %d", user_id)
            return True

        return False

    def get_acknowledgment_stats(self) -> Dict[str, Any]:
        """Get statistics about acknowledgments."""
        total_users = self.run_query(
            "SELECT COUNT(*) as c FROM user_acknowledgments",
            one=True
        )

        fully_acknowledged = self.run_query(
            "SELECT COUNT(*) as c FROM user_acknowledgments WHERE all_acknowledged = 1",
            one=True
        )

        by_item = {}
        for key, info in ACKNOWLEDGMENT_TEXTS.items():
            field = info["db_field"]
            result = self.run_query(
                f"SELECT COUNT(*) as c FROM user_acknowledgments WHERE {field} = 1",
                one=True
            )
            by_item[key] = result["c"] if result else 0

        return {
            "total_users_started": total_users["c"] if total_users else 0,
            "fully_acknowledged": fully_acknowledged["c"] if fully_acknowledged else 0,
            "by_item": by_item,
            "current_version": ACKNOWLEDGMENT_VERSION,
        }
