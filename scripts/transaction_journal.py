"""Crash-safe, no-duplicate transaction journaling.

The journal is intentionally local provenance, not chain evidence.  A write
operation is reserved before a sender is called; once a hash is returned it is
stored atomically before any polling.  A reserved operation may never be
rebroadcast automatically, including after a timeout or client exception.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any


HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
SCHEMA = "sentinelx-transaction-journal-v1"


class JournalError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_hash(value: str) -> str:
    if not HASH_RE.fullmatch(value):
        raise JournalError("transaction hash must be a 32-byte 0x-prefixed hash")
    return value.lower()


class TransactionJournal:
    """Persist operation state with atomic replace and fsync semantics."""

    def __init__(self, path: Path):
        self.path = path

    def _empty(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "operations": {}}

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise JournalError(f"transaction journal is unreadable: {error}") from error
        if (not isinstance(document, dict) or document.get("schema") != SCHEMA
                or not isinstance(document.get("operations"), dict)):
            raise JournalError("transaction journal schema is invalid")
        return document

    def _save(self, document: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            # Windows security/indexing software can briefly hold a freshly
            # written JSON destination. Retry the replace without changing
            # the atomic-write guarantee or weakening journal persistence.
            for attempt in range(8):
                try:
                    os.replace(temporary, self.path)
                    break
                except PermissionError:
                    if attempt == 7:
                        raise
                    time.sleep(0.25)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise JournalError(f"cannot persist transaction journal: {error}") from error

    def reserve_broadcast(self, operation: str, **metadata: Any) -> dict[str, Any]:
        if not operation or operation in (".", "..") or "/" in operation or "\\" in operation:
            raise JournalError("operation name is invalid")
        document = self.load()
        operations = document["operations"]
        if operation in operations:
            raise JournalError(f"operation {operation!r} is already reserved; reconcile it")
        record: dict[str, Any] = {
            "operation": operation,
            "state": "BROADCAST_RESERVED",
            "reserved_at": _utc_now(),
            **metadata,
        }
        operations[operation] = record
        self._save(document)
        return record.copy()

    def record_submission(
        self,
        operation: str,
        returned_hash: str,
        *,
        transaction_kind: str = "genlayer",
        parent_operation: str | None = None,
    ) -> dict[str, Any]:
        document = self.load()
        record = document["operations"].get(operation)
        if not isinstance(record, dict) or record.get("state") != "BROADCAST_RESERVED":
            raise JournalError("submission requires a reserved operation")
        if record.get("tx_hash"):
            raise JournalError("operation already has a submitted hash")
        tx_hash = _validate_hash(returned_hash)
        if any(
            isinstance(item, dict) and item.get("tx_hash") == tx_hash
            for item in document["operations"].values()
        ):
            raise JournalError("returned transaction hash is already journaled")
        record.update({
            "state": "SUBMITTED",
            "tx_hash": tx_hash,
            "transaction_kind": transaction_kind,
            "parent_operation": parent_operation,
            "submitted_at": _utc_now(),
        })
        self._save(document)
        return record.copy()

    def update(self, operation: str, **fields: Any) -> dict[str, Any]:
        document = self.load()
        record = document["operations"].get(operation)
        if not isinstance(record, dict):
            raise JournalError(f"operation {operation!r} is not journaled")
        record.update(fields)
        record["updated_at"] = _utc_now()
        self._save(document)
        return record.copy()

    def mark_not_broadcast(
        self,
        operation: str,
        *,
        latest_nonce: int,
        pending_nonce: int,
        verification: str,
    ) -> dict[str, Any]:
        """Close a no-hash CLI attempt only after nonce convergence is proved.

        A reserved operation without a transaction hash is normally terminally
        ambiguous.  This narrower transition is allowed only when the caller
        has independently checked that latest and pending nonce are equal and
        the record still contains no hash.  The original attempt remains in
        the journal and can never be silently reused or overwritten.
        """
        if not verification:
            raise JournalError("broadcast-absence verification is required")
        if int(latest_nonce) != int(pending_nonce):
            raise JournalError("nonce convergence is required to close a no-hash attempt")
        document = self.load()
        record = document["operations"].get(operation)
        if not isinstance(record, dict):
            raise JournalError(f"operation {operation!r} is not journaled")
        if record.get("tx_hash"):
            raise JournalError("a submitted operation cannot be marked not broadcast")
        if record.get("state") not in ("BROADCAST_RESERVED", "BROADCAST_CALL_RAISED"):
            raise JournalError("operation is not an unsubmitted CLI attempt")
        record.update({
            "state": "BLOCKED_BEFORE_BROADCAST",
            "broadcast_verified_absent": True,
            "broadcast_absence_verification": verification,
            "latest_nonce_at_verification": int(latest_nonce),
            "pending_nonce_at_verification": int(pending_nonce),
        })
        record["updated_at"] = _utc_now()
        self._save(document)
        return record.copy()

    def record_child(
        self,
        parent_operation: str,
        operation: str,
        returned_hash: str,
        **metadata: Any,
    ) -> dict[str, Any]:
        parent = self.load()["operations"].get(parent_operation)
        if not isinstance(parent, dict) or not parent.get("tx_hash"):
            raise JournalError("child requires a parent with a persisted hash")
        self.reserve_broadcast(operation, parent_operation=parent_operation, **metadata)
        return self.record_submission(
            operation,
            returned_hash,
            parent_operation=parent_operation,
        )
