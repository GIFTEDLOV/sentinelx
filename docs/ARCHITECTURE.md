# SentinelX architecture

SentinelX V2 is a pre-canonical multi-target governor and protected-target
architecture for GenLayer. V1 is the historical pre-canonical prototype at
commit `7e3b552c8b0471db0411206fdbc743dd12ef4e80`; it remains in history and
has not been deployed canonically. The V2 source and state layout are a new
first-deployment design, so V1 storage migration is not required.

## Trust boundary

The governor registers an immutable `TargetPolicy`, including the Release
Constitution, bounded authority namespaces, immutable raw-commit prefixes and
an explicit `OPTIONAL` or `REQUIRED_INDEPENDENT` security-attestation mode.
Each proposal freezes the target, parent snapshot, candidate bytes and hash,
release intent, evidence IDs, policy fingerprint and deadlines.

Before review, `capture_evidence` independently retrieves and authenticates
the exact parent source, frozen candidate source, CI evidence and optional or
required security evidence. Only consensus on the complete result writes a
write-once, proposal-bound `EvidenceSnapshotRecord`.

Semantic review consumes the stored snapshot and performs zero live web
fetches. Validators independently compare the exact 14-field boolean result;
only fourteen `true` values can queue installation. The constitution, sources
and evidence are untrusted data inside explicit prompt delimiters, so embedded
instructions cannot become authorization.

`protected_app_v1.py` is the V2 baseline target name retained for source
lineage. Its historical field prefix is preserved and its owner is not a Root
upgrader. The safe V2 candidate appends only `release_note`; the unsafe
candidate is test-only and demonstrates storage, authority and value-flow
violations.

## State and recovery

The lifecycle is `PROPOSED → EVIDENCE_READY → review → UPGRADE_QUEUED →
VERIFIED`. Retrieval failures are retryable; authenticated evidence defects are
repairable. Evidence identity is derived from committed hashes and identifiers,
not URL availability. Exact-byte mirrors may be used as recovery transport.
Snapshots are write-once and bounded views expose hashes, IDs, provenance and
the snapshot digest without exposing raw bytes through the public view.

Finalized installation remains separately reconciled. Accepted is not
finalized, finalized execution failure is not success, and an ambiguous child
is never authorization. The operational transaction order is precondition read
→ fresh fee quote → one broadcast → immediate hash persistence → same-hash
reconciliation → finality → execution result → expected-state readback.

The direct suite uses a deterministic in-memory V2 model for architecture
coverage without fabricating network transactions.
