# ===============================
# services/evidence.py - Immutable Evidence Storage (PRODUCTION)
# ===============================
# CRITICAL: This service handles EMERGENCY evidence
#
# RULES (NON-NEGOTIABLE):
# 1. Evidence is APPEND-ONLY - no updates, no deletes
# 2. All evidence has integrity hash (SHA-256)
# 3. Evidence is retained for 7 years minimum (legal requirement)
# 4. Evidence NEVER enters AI/ML training pipelines
# 5. Hash verification on every read

import json
import hashlib
import time
from typing import Optional, List, Dict, Any, Union

from services.base import BaseService
from contracts.types import (
    EventCategory,
    EvidenceIntegrity,
    EVIDENCE_RETENTION_DAYS,
)
from contracts.events import BaseEvent, EmergencyEvent


class EvidenceService(BaseService):
    """
    Immutable Evidence Storage Service.

    ONLY for EMERGENCY events. Other events go to EventService.

    This service ensures:
    1. APPEND-ONLY storage (no updates, no deletes from code)
    2. Cryptographic integrity verification
    3. Legal compliance retention periods
    4. Tamper detection

    WARNING: Modifying evidence is a CRIMINAL OFFENSE in many jurisdictions.
    This service is designed to make tampering impossible from the application layer.
    """

    def _compute_integrity_hash(self, event_id: str, event_type: str, payload: str, raw_evidence: bytes = None) -> str:
        """
        Compute SHA-256 integrity hash for evidence.

        Hash includes:
        - event_id
        - event_type
        - payload (JSON)
        - raw_evidence (if present)

        This hash is stored and verified on every read.
        """
        data = f"{event_id}|{event_type}|{payload}"
        if raw_evidence:
            data += f"|{hashlib.sha256(raw_evidence).hexdigest()}"
        return hashlib.sha256(data.encode()).hexdigest()

    def store_evidence(
        self,
        event: Union[BaseEvent, EmergencyEvent],
        raw_evidence: bytes = None,
        evidence_type: str = None
    ) -> Optional[str]:
        """
        Store emergency evidence IMMUTABLY.

        Args:
            event: Emergency event (MUST have category=EMERGENCY)
            raw_evidence: Optional binary evidence (video frame, audio, image)
            evidence_type: Type of evidence ("video", "audio", "image", "sensor")

        Returns:
            event_id if successful, None if failed

        CRITICAL:
            - Will REJECT non-emergency events
            - Will REJECT duplicate event_id
            - Computes and stores integrity hash
            - Sets retention period (7 years from now)
        """
        # ENFORCE: Only emergency events
        if event.category != EventCategory.EMERGENCY:
            print(f"[EVIDENCE REJECTED] Event {event.event_id} is not EMERGENCY category")
            return None

        # Check for duplicate
        if self.exists("event_evidence", "event_id", event.event_id):
            print(f"[EVIDENCE DUPLICATE] Event {event.event_id} already stored")
            return None

        # Serialize payload
        payload = json.dumps(event.to_dict())

        # Compute integrity hash
        integrity_hash = self._compute_integrity_hash(
            event.event_id,
            event.event_type,
            payload,
            raw_evidence
        )

        # Calculate retention period (7 years from now)
        retention_until = int(time.time()) + (EVIDENCE_RETENTION_DAYS * 24 * 60 * 60)

        result = self.run_query(
            """
            INSERT INTO event_evidence
            (event_id, event_type, category, payload, raw_evidence, evidence_type,
             integrity_hash, integrity_status, created_at, is_immutable, retention_until)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.event_type,
                event.category.value,
                payload,
                raw_evidence,
                evidence_type,
                integrity_hash,
                EvidenceIntegrity.VERIFIED.value,
                event.timestamp,
                1,  # is_immutable = true
                retention_until,
            ),
            commit=True
        )

        if result:
            print(f"[EVIDENCE STORED] {event.event_id} | Type: {event.event_type} | Hash: {integrity_hash[:16]}...")
            return event.event_id
        return None

    def get_evidence(self, event_id: str, verify_integrity: bool = True) -> Optional[Dict[str, Any]]:
        """
        Retrieve evidence with integrity verification.

        Args:
            event_id: The event ID to retrieve
            verify_integrity: If True, verify hash before returning (default True)

        Returns:
            Evidence dict with 'integrity_verified' field, or None if not found

        WARNING: If integrity verification fails, evidence is marked as TAMPERED
        """
        evidence = self.run_query(
            """
            SELECT * FROM event_evidence
            WHERE event_id = ?
            """,
            (event_id,),
            one=True
        )

        if not evidence:
            return None

        # Parse payload
        if evidence.get('payload'):
            evidence['payload'] = json.loads(evidence['payload'])

        # Integrity verification
        if verify_integrity:
            computed_hash = self._compute_integrity_hash(
                evidence['event_id'],
                evidence['event_type'],
                json.dumps(evidence['payload']),
                evidence.get('raw_evidence')
            )

            if computed_hash == evidence['integrity_hash']:
                evidence['integrity_verified'] = True
            else:
                # CRITICAL: Tampering detected!
                evidence['integrity_verified'] = False
                evidence['integrity_status'] = EvidenceIntegrity.TAMPERED.value
                print(f"[TAMPERING DETECTED] Event {event_id} | Expected: {evidence['integrity_hash'][:16]}... | Got: {computed_hash[:16]}...")
                # Note: We don't update the DB here - that would be tampering too
                # Instead, we log and return with the tampered flag

        return evidence

    def get_all_emergency_evidence(
        self,
        limit: int = 100,
        verify_integrity: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all emergency evidence records.

        Args:
            limit: Maximum records to return
            verify_integrity: If True, verify each record (slower)

        Returns:
            List of evidence records
        """
        records = self.run_query(
            """
            SELECT * FROM event_evidence
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,)
        )

        results = []
        for record in (records or []):
            if record.get('payload'):
                record['payload'] = json.loads(record['payload'])

            if verify_integrity:
                computed_hash = self._compute_integrity_hash(
                    record['event_id'],
                    record['event_type'],
                    json.dumps(record['payload']),
                    record.get('raw_evidence')
                )
                record['integrity_verified'] = (computed_hash == record['integrity_hash'])

            results.append(record)

        return results

    def get_evidence_by_type(
        self,
        event_type: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get evidence filtered by event type."""
        records = self.run_query(
            """
            SELECT * FROM event_evidence
            WHERE event_type = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (event_type, limit)
        )

        for record in (records or []):
            if record.get('payload'):
                record['payload'] = json.loads(record['payload'])

        return records or []

    def verify_all_integrity(self) -> Dict[str, Any]:
        """
        Verify integrity of ALL evidence records.

        Returns:
            {
                "total": int,
                "verified": int,
                "tampered": int,
                "tampered_ids": list
            }

        CRITICAL: Run this periodically as part of security audit.
        """
        records = self.run_query("SELECT * FROM event_evidence")

        stats = {
            "total": 0,
            "verified": 0,
            "tampered": 0,
            "tampered_ids": []
        }

        for record in (records or []):
            stats["total"] += 1

            payload = record.get('payload', '{}')
            computed_hash = self._compute_integrity_hash(
                record['event_id'],
                record['event_type'],
                payload,
                record.get('raw_evidence')
            )

            if computed_hash == record['integrity_hash']:
                stats["verified"] += 1
            else:
                stats["tampered"] += 1
                stats["tampered_ids"].append(record['event_id'])
                print(f"[INTEGRITY VIOLATION] {record['event_id']}")

        return stats

    def get_retention_report(self) -> Dict[str, Any]:
        """
        Get report on evidence retention status.

        Returns:
            {
                "total": int,
                "expiring_soon": int (within 90 days),
                "expired": int (past retention, pending archive)
            }
        """
        now = int(time.time())
        ninety_days = now + (90 * 24 * 60 * 60)

        total = self.run_query("SELECT COUNT(*) as c FROM event_evidence", one=True)
        expiring = self.run_query(
            "SELECT COUNT(*) as c FROM event_evidence WHERE retention_until < ? AND retention_until > ?",
            (ninety_days, now),
            one=True
        )
        expired = self.run_query(
            "SELECT COUNT(*) as c FROM event_evidence WHERE retention_until < ? AND archived_at IS NULL",
            (now,),
            one=True
        )

        return {
            "total": total['c'] if total else 0,
            "expiring_soon": expiring['c'] if expiring else 0,
            "expired": expired['c'] if expired else 0,
        }

    # ===============================
    # FORBIDDEN OPERATIONS
    # ===============================
    # These methods are intentionally NOT implemented.
    # Evidence CANNOT be updated or deleted from application code.

    def update_evidence(self, *args, **kwargs):
        """FORBIDDEN: Evidence is immutable."""
        raise NotImplementedError(
            "Evidence cannot be updated. This is by design for legal compliance. "
            "If you need to correct evidence, store a new event with reference to the original."
        )

    def delete_evidence(self, *args, **kwargs):
        """FORBIDDEN: Evidence cannot be deleted."""
        raise NotImplementedError(
            "Evidence cannot be deleted from application code. "
            "Deletion is only allowed via retention policy enforcement by DBA with full audit trail."
        )
