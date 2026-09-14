# SentinelX threat model

## Protected assets

- The exact currently installed code and its SHA-256 identity.
- The immutable release constitution and policy fingerprint.
- Owner/user rights, the governor upgrade authority, and safe fund flow.
- The integrity and freshness of CI/security attestations.
- Finalized installation state and its post-install attestation.

## Adversaries and controls

An owner may submit a malicious release or attempt a direct upgrade. The target
does not put the owner in `Root.upgraders`; installation requires the governor
sender, an exact live authorization, a matching proposal ID/hash, and a
finalized confirmation.

A proposer may replay a safe candidate, evidence ID, branch URL, mutable ref,
or path alias. Candidate bytes and hashes are frozen, installed candidate keys
are remembered per target, evidence IDs are globally reserved by kind, and
source/evidence URLs must be ASCII canonical raw GitHub paths containing a
lowercase 40-hex commit. Queries, fragments, percent escapes, backslashes,
repeated separators, dot segments, dot-dot segments, and mutable branches are
rejected.

An evidence publisher may bind an attestation to another target, parent,
candidate, issuer, or policy. The governor checks every binding and requires
distinct CI/security IDs, distinct authority namespaces, and a security raw
publisher owner different from the source publisher owner. The implementation
uses the configured authority namespace as the authentication boundary; a
future deployment may add cryptographic publisher signatures without changing
the binding rules.

An external fetch or semantic model may fail or return malformed data. Fetch
and model failures remain retryable, while malformed/stale/wrongly bound
evidence remains repairable. A semantic result is authorized only when every
required boolean is exactly `True`; no score, confidence, majority, or prose
can authorize it.

A transaction may be accepted but not finalized, finalize without successful
execution, or finalize with unexpected target state. The operational contract
is precondition read → fee estimate → one broadcast → immediate hash
persistence → same-hash reconciliation → lifecycle/result/state checks.
Timeout handling reconciles only an exact finalized installation or fails from
a known parent state; it never blindly rebroadcasts.

## Residual assumptions

Phase 2A does not claim a deployed address, transaction hash, publisher key
signature, or live network execution. The CI workflow is a same-owner CI
authority, not an independent security publisher. Semantic equivalence remains a validator
judgment constrained by the constitution and exact vector, not a formal proof
of arbitrary Python behavior. The unsafe V2 file is intentionally retained for
negative testing only.
