# SentinelX V2 threat model

## Protected assets

- Exact installed code and SHA-256 identity.
- Immutable Release Constitution and policy fingerprint.
- Owner/user rights, governor upgrade authority and safe fund flow.
- Exact authenticated evidence snapshots and freshness decisions.
- Finalized installation state and post-install attestation.

## Adversaries and controls

An owner may submit a malicious release or attempt a direct upgrade. The target
does not put the owner in `Root.upgraders`; installation requires the governor
sender, exact live authorization, matching proposal ID/hash and finalized
confirmation.

A proposer may replay a candidate, evidence ID, branch URL or mutable ref.
Candidate bytes and hashes are frozen, installed candidate keys are remembered,
evidence IDs are globally reserved, and URLs are restricted to canonical raw
GitHub commit paths. Snapshot identity is based on committed hashes and IDs,
so URL recovery cannot silently change substantive evidence.

A remote publisher may bind an artifact to another target, parent, candidate,
issuer or policy. Capture checks every binding, schema, exact body hash,
freshness, expiry and required CI checks. In `REQUIRED_INDEPENDENT`, security
authority, prefix, artifact and distinct raw GitHub owner are mandatory. In
`OPTIONAL`, absent security evidence is a legitimate non-audit state and the
validators must still decide from authenticated source and CI data.

An evidence source may contain prompt injection or a fake verdict. All remote
content is untrusted data. Capture authenticates it before snapshotting;
semantic review performs no remote fetch and uses only the stored snapshot.
Only the complete exact 14-field boolean vector drives authorization.

A snapshot may be tampered with or partially written. Snapshot writes happen
only after consensus on a complete capture result, the record is write-once by
identity, all component hashes are rechecked before review, and the persisted
digest is verified.

A transaction may be accepted but not finalized, finalize with execution
failure, or leave an ambiguous child. The transaction contract is precondition
read → fresh fee estimate → one broadcast → immediate hash persistence →
same-hash reconciliation → finality/result/state checks. Timeout and repair
paths never blindly rebroadcast.

## Residual assumptions

V2 is a source/test freeze, not a deployment or external security audit. The
CI publisher is not an independent security publisher. Semantic equivalence is
a validator judgment constrained by the constitution and vector, not a formal
proof of arbitrary Python behavior. The unsafe candidate remains test-only.
