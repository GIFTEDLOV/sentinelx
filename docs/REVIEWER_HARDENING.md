# SentinelX reviewer hardening

This document records the invariants that were checked in the final frontend and repository hardening pass. It does not claim an external audit; the canonical release used OPTIONAL security attestation.

| Failure class | SentinelX invariant | Implementation and proof |
| --- | --- | --- |
| Committed evidence liveness | Remote interruption cannot create a ready snapshot or bypass authenticated staged bytes. | Deterministic staging, compact remote attestation, retry/repair statuses, exact-byte mirror checks, write-once snapshots, and the evidence/replay cases in `tests/direct/test_sentinelx_v2_model.py`. Review reads stored authenticated bytes and records zero web fetches. |
| Unassessed vs consensus-cleared | A proposal is not installed merely because it exists or has staged evidence. | Contract statuses remain distinct through `VERIFIED`; the UI maps `PROPOSED`, `EVIDENCE_STAGED`, `EVIDENCE_READY`, `UPGRADE_QUEUED`, `REJECTED`, failures, expiry, and cancellation separately. Frontend lifecycle-label tests cover the distinction. |
| Owner suppression or bypass | Withholding review blocks the owner’s release; it cannot authorize installation. | The target accepts upgrades only from the governor, and the governor requires an approved `UPGRADE_QUEUED` proposal. The direct model and mutation gates cover owner bypass, rejected execution, expiry, cancellation, and replay barriers. |
| Trusted authority binding | Evidence is bound to issuer, target, proposal, parent/candidate hashes, policy, kind, identity, authority prefix, and time bounds. | Binding, stale/future/expired, wrong-authority, replay, and cross-target cases are covered by the direct and mutation suites. |
| Wrong-object or reassessment confusion | Every operation is keyed by the requested target and proposal; no first-open-object shortcut is permitted. | Proposal/target fields are checked in the contract model and adversarial suite. Frontend transaction records are now keyed by returned hash, while dashboard reads derive each row from its own target and proposal status. |
| Finality and retry safety | `ACCEPTED` or a polling timeout is never success and never triggers a blind rebroadcast. | Write tracking persists the returned hash before polling, requires finalized plus `FINISHED_WITH_RETURN`, tracks children independently, and resumes the same hash. The frontend transaction store tolerates corrupt/old storage and preserves same-operation distinct hashes. |

The deployed V2.3 contract source hashes were rechecked and were not changed by this hardening pass. No new chain write or contract deployment was performed.
