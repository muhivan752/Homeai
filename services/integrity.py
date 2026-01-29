# ===============================
# services/integrity.py - Hash Chain & External Anchoring (PRODUCTION)
# ===============================
# CRITICAL: SQLite is NOT sufficient for legal evidence immutability
#
# This service provides:
# 1. Internal hash chain (append-only verification)
# 2. Daily hash digests for external anchoring
# 3. Tamper detection via chain verification
#
# For TRUE legal compliance, external anchoring must be done to:
# - Blockchain (e.g., Ethereum, Bitcoin via OpenTimestamps)
# - Trusted timestamping service (e.g., RFC 3161)
# - External audit service
#
# This service prepares the data; actual external anchoring
# is handled by external systems.

import json
import hashlib
import time
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from services.base import BaseService


logger = logging.getLogger("homeai.integrity")


class IntegrityService(BaseService):
    """
    Hash Chain & External Anchoring Service.

    ARCHITECTURE:
    ┌─────────────────────────────────────────────────────────────┐
    │                    HASH CHAIN MODEL                          │
    │                                                              │
    │  Block 0 (Genesis)                                          │
    │  ├── hash: sha256("GENESIS")                                │
    │  ├── prev_hash: null                                        │
    │  └── timestamp: <init_time>                                 │
    │            │                                                 │
    │            ▼                                                 │
    │  Block 1                                                     │
    │  ├── hash: sha256(evidence_hashes + prev_hash)              │
    │  ├── prev_hash: Block 0 hash                                │
    │  ├── evidence_ids: [...]                                    │
    │  └── timestamp: <block_time>                                │
    │            │                                                 │
    │            ▼                                                 │
    │  Block N (Latest)                                            │
    │  └── ...                                                     │
    └─────────────────────────────────────────────────────────────┘

    WHY THIS MATTERS:
    - If any evidence is modified, its hash changes
    - If any hash changes, the block hash changes
    - If any block hash changes, ALL subsequent blocks become invalid
    - This makes tampering detectable (but not impossible)

    FOR TRUE IMMUTABILITY:
    - Export daily digests and anchor to external systems
    - The external anchor proves the state at that time
    - Even if DB is modified, external anchor reveals tampering
    """

    def __init__(self, db_path: str):
        super().__init__(db_path)
        self._ensure_tables()
        self._ensure_genesis_block()

    def _ensure_tables(self):
        """Create integrity tables if not exist."""
        self.run_query("""
            CREATE TABLE IF NOT EXISTS hash_chain (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                block_hash TEXT UNIQUE NOT NULL,
                prev_hash TEXT,
                evidence_count INTEGER NOT NULL,
                evidence_ids TEXT NOT NULL,
                merkle_root TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                anchored_at INTEGER,
                anchor_reference TEXT,
                anchor_type TEXT
            )
        """, commit=True)

        self.run_query("""
            CREATE INDEX IF NOT EXISTS idx_hash_chain_time
            ON hash_chain(created_at DESC)
        """, commit=True)

    def _ensure_genesis_block(self):
        """Create genesis block if not exists."""
        genesis = self.run_query(
            "SELECT * FROM hash_chain WHERE prev_hash IS NULL",
            one=True
        )

        if not genesis:
            genesis_hash = hashlib.sha256(b"HOMEAI_GENESIS_BLOCK").hexdigest()
            self.run_query(
                """
                INSERT INTO hash_chain
                (block_hash, prev_hash, evidence_count, evidence_ids, merkle_root, created_at)
                VALUES (?, NULL, 0, '[]', ?, ?)
                """,
                (genesis_hash, genesis_hash, int(time.time())),
                commit=True
            )
            logger.info("Genesis block created: %s", genesis_hash[:16])

    def _compute_merkle_root(self, hashes: List[str]) -> str:
        """
        Compute Merkle root of a list of hashes.

        Merkle tree provides efficient verification of large datasets.
        """
        if not hashes:
            return hashlib.sha256(b"EMPTY").hexdigest()

        # Ensure even number of leaves
        if len(hashes) % 2 == 1:
            hashes = hashes + [hashes[-1]]

        # Build tree bottom-up
        while len(hashes) > 1:
            next_level = []
            for i in range(0, len(hashes), 2):
                combined = hashes[i] + hashes[i + 1]
                next_level.append(hashlib.sha256(combined.encode()).hexdigest())
            hashes = next_level

        return hashes[0]

    def create_block(self, evidence_ids: List[str] = None) -> Optional[Dict[str, Any]]:
        """
        Create a new block in the hash chain.

        Collects all unanchored evidence, computes merkle root,
        and links to previous block.

        Args:
            evidence_ids: Optional specific IDs to include.
                         If None, includes all unanchored evidence.

        Returns:
            Block info dict or None if no evidence to anchor
        """
        # Get latest block
        latest = self.run_query(
            "SELECT * FROM hash_chain ORDER BY id DESC LIMIT 1",
            one=True
        )
        prev_hash = latest['block_hash'] if latest else None

        # Get evidence to include
        if evidence_ids is None:
            # Get all evidence not yet in any block
            # This requires tracking which evidence is in which block
            # For simplicity, get evidence created since last block
            last_block_time = latest['created_at'] if latest else 0
            evidence_records = self.run_query(
                """
                SELECT event_id, integrity_hash FROM event_evidence
                WHERE created_at > ?
                ORDER BY created_at
                """,
                (last_block_time,)
            ) or []
            evidence_ids = [r['event_id'] for r in evidence_records]
            evidence_hashes = [r['integrity_hash'] for r in evidence_records]
        else:
            # Get hashes for specified IDs
            if not evidence_ids:
                logger.warning("No evidence IDs provided for block creation")
                return None

            placeholders = ','.join(['?' for _ in evidence_ids])
            evidence_records = self.run_query(
                f"""
                SELECT event_id, integrity_hash FROM event_evidence
                WHERE event_id IN ({placeholders})
                """,
                tuple(evidence_ids)
            ) or []
            evidence_hashes = [r['integrity_hash'] for r in evidence_records]

        if not evidence_hashes:
            logger.info("No new evidence to anchor")
            return None

        # Compute merkle root
        merkle_root = self._compute_merkle_root(evidence_hashes)

        # Compute block hash
        block_data = f"{prev_hash or 'GENESIS'}|{merkle_root}|{json.dumps(sorted(evidence_ids))}"
        block_hash = hashlib.sha256(block_data.encode()).hexdigest()

        # Store block
        now = int(time.time())
        result = self.run_query(
            """
            INSERT INTO hash_chain
            (block_hash, prev_hash, evidence_count, evidence_ids, merkle_root, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                block_hash,
                prev_hash,
                len(evidence_ids),
                json.dumps(evidence_ids),
                merkle_root,
                now,
            ),
            commit=True
        )

        if result:
            logger.info(
                "Block created: %s | Evidence: %d | Merkle: %s",
                block_hash[:16], len(evidence_ids), merkle_root[:16]
            )
            return {
                "block_hash": block_hash,
                "prev_hash": prev_hash,
                "evidence_count": len(evidence_ids),
                "merkle_root": merkle_root,
                "created_at": now,
            }

        return None

    def verify_chain(self) -> Dict[str, Any]:
        """
        Verify entire hash chain integrity.

        Returns:
            {
                "valid": bool,
                "total_blocks": int,
                "total_evidence": int,
                "invalid_blocks": list (empty if valid),
                "errors": list
            }
        """
        blocks = self.run_query(
            "SELECT * FROM hash_chain ORDER BY id ASC"
        ) or []

        result = {
            "valid": True,
            "total_blocks": len(blocks),
            "total_evidence": 0,
            "invalid_blocks": [],
            "errors": [],
        }

        prev_hash = None

        for block in blocks:
            result["total_evidence"] += block['evidence_count']

            # Verify prev_hash link
            if block['prev_hash'] != prev_hash:
                result["valid"] = False
                result["invalid_blocks"].append(block['id'])
                result["errors"].append(
                    f"Block {block['id']}: prev_hash mismatch. Expected {prev_hash}, got {block['prev_hash']}"
                )

            # Verify block hash
            evidence_ids = json.loads(block['evidence_ids'])
            expected_data = f"{block['prev_hash'] or 'GENESIS'}|{block['merkle_root']}|{json.dumps(sorted(evidence_ids))}"
            expected_hash = hashlib.sha256(expected_data.encode()).hexdigest()

            if expected_hash != block['block_hash']:
                result["valid"] = False
                result["invalid_blocks"].append(block['id'])
                result["errors"].append(
                    f"Block {block['id']}: block_hash mismatch. Expected {expected_hash[:16]}..., got {block['block_hash'][:16]}..."
                )

            prev_hash = block['block_hash']

        logger.info(
            "Chain verification: %s | Blocks: %d | Evidence: %d",
            "VALID" if result["valid"] else "INVALID",
            result["total_blocks"],
            result["total_evidence"]
        )

        return result

    def get_daily_digest(self, date: str = None) -> Dict[str, Any]:
        """
        Generate daily digest for external anchoring.

        This digest should be anchored to external systems
        (blockchain, timestamping service, etc.)

        Args:
            date: Date string (YYYY-MM-DD). Defaults to today.

        Returns:
            {
                "date": str,
                "digest_hash": str,
                "block_count": int,
                "evidence_count": int,
                "first_block": str,
                "last_block": str,
                "generated_at": int
            }
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Parse date to get timestamp range
        date_start = datetime.strptime(date, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0, tzinfo=timezone.utc
        )
        date_end = datetime.strptime(date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )

        start_ts = int(date_start.timestamp())
        end_ts = int(date_end.timestamp())

        # Get blocks for this day
        blocks = self.run_query(
            """
            SELECT * FROM hash_chain
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY id ASC
            """,
            (start_ts, end_ts)
        ) or []

        if not blocks:
            return {
                "date": date,
                "digest_hash": None,
                "block_count": 0,
                "evidence_count": 0,
                "message": "No blocks for this date",
            }

        # Compute digest
        block_hashes = [b['block_hash'] for b in blocks]
        evidence_count = sum(b['evidence_count'] for b in blocks)

        digest_data = f"{date}|{json.dumps(block_hashes)}"
        digest_hash = hashlib.sha256(digest_data.encode()).hexdigest()

        return {
            "date": date,
            "digest_hash": digest_hash,
            "block_count": len(blocks),
            "evidence_count": evidence_count,
            "first_block": blocks[0]['block_hash'],
            "last_block": blocks[-1]['block_hash'],
            "generated_at": int(time.time()),
        }

    def record_external_anchor(
        self,
        block_hash: str,
        anchor_type: str,
        anchor_reference: str,
    ) -> bool:
        """
        Record that a block has been anchored externally.

        Args:
            block_hash: The block that was anchored
            anchor_type: Type of anchor ("blockchain", "rfc3161", "external_audit")
            anchor_reference: Reference to external anchor (tx hash, receipt ID, etc.)

        Returns:
            True if recorded, False if block not found
        """
        result = self.run_query(
            """
            UPDATE hash_chain
            SET anchored_at = ?, anchor_type = ?, anchor_reference = ?
            WHERE block_hash = ?
            """,
            (int(time.time()), anchor_type, anchor_reference, block_hash),
            commit=True
        )

        if result and result > 0:
            logger.info(
                "External anchor recorded: Block %s | Type: %s | Ref: %s",
                block_hash[:16], anchor_type, anchor_reference
            )
            return True

        return False

    def get_latest_block(self) -> Optional[Dict[str, Any]]:
        """Get the latest block in the chain."""
        block = self.run_query(
            "SELECT * FROM hash_chain ORDER BY id DESC LIMIT 1",
            one=True
        )
        if block and block.get('evidence_ids'):
            block['evidence_ids'] = json.loads(block['evidence_ids'])
        return block

    def get_anchor_status(self) -> Dict[str, Any]:
        """
        Get anchoring status report.

        Returns:
            {
                "total_blocks": int,
                "anchored_blocks": int,
                "unanchored_blocks": int,
                "latest_anchored": dict or None,
                "anchor_types": dict (type -> count)
            }
        """
        total = self.run_query(
            "SELECT COUNT(*) as c FROM hash_chain",
            one=True
        )

        anchored = self.run_query(
            "SELECT COUNT(*) as c FROM hash_chain WHERE anchored_at IS NOT NULL",
            one=True
        )

        latest_anchored = self.run_query(
            """
            SELECT * FROM hash_chain
            WHERE anchored_at IS NOT NULL
            ORDER BY anchored_at DESC
            LIMIT 1
            """,
            one=True
        )

        anchor_types = self.run_query(
            """
            SELECT anchor_type, COUNT(*) as count
            FROM hash_chain
            WHERE anchor_type IS NOT NULL
            GROUP BY anchor_type
            """
        ) or []

        return {
            "total_blocks": total['c'] if total else 0,
            "anchored_blocks": anchored['c'] if anchored else 0,
            "unanchored_blocks": (total['c'] if total else 0) - (anchored['c'] if anchored else 0),
            "latest_anchored": latest_anchored,
            "anchor_types": {r['anchor_type']: r['count'] for r in anchor_types},
        }
