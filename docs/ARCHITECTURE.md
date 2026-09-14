# SentinelX architecture

SentinelX Phase 1 contains a multi-target governor and a protected target
reference implementation. It is source-complete for local review; it has not
been deployed.

## Trust boundary

`sentinelx_governor.py` is the policy registry and release state machine.
Each target registers once. The registration stores an immutable
`TargetPolicy`, including the release constitution, authority namespaces, and
immutable raw-commit URL prefixes. Registration fields are not owner-editable;
only the current release identity advances after exact verified installation.

Each `ReleaseProposal` freezes its target, parent snapshot, candidate bytes,
candidate SHA-256, candidate source URL, evidence URLs and IDs, evidence-set
hash, policy fingerprint, release intent, and deadlines. Evidence IDs are
reserved globally, independent of evidence kind, so cancellation cannot make
an attestation replayable on another target.

The governor authenticates immutable source and evidence before asking the
nondeterministic model for the semantic result. The leader and validators each
repeat retrieval, hash, binding, publisher, freshness, and evidence checks.
Only exact agreement on the identity fields, result/error class, decision, and
all 14 semantic booleans can authorize an upgrade.

`protected_app_v1.py` adds only the governor to `Root.upgraders`. An owner can
change application data and initiate one-time registration, but cannot replace
code. Installation is reachable only through a governor-sender check, repeats
live authorization and candidate identity checks, stores an installation
attestation, and sends finalized confirmation back to the governor.

`protected_app_v2_safe.py` preserves the v1 field prefix, owner rights, and
governor authority, then appends a release-note feature. The unsafe candidate
is intentionally test-only: it shifts storage, exposes owner code replacement,
permits governor rewriting and privileged mutation, and contains an unsafe
value flow. It is never the canonical upgrade candidate.

## State and recovery

Temporary fetch/model failures use `REVIEW_RETRY_REQUIRED`; malformed or
expired authenticated evidence uses `EVIDENCE_REPAIR_REQUIRED`; semantic
disagreement or a failed safety vector is `REJECTED`. Queued installations
expire at their execution deadline. A finalized exact installation may be
reconciled without rebroadcast; an unknown or late child cannot install after
authorization expiry.

Reads are bounded by explicit target, proposal, and history capacities. The
direct suite uses a deterministic in-memory model to exercise these invariants
without fabricating network transactions.
