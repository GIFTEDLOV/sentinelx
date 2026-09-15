# SentinelX V2 semantic review contract

The authorization-driving safety vector has exactly these 14 fields, in order:

1. `storage_layout_compatible`
2. `public_interface_compatible`
3. `user_rights_preserved`
4. `no_privilege_escalation`
5. `upgrade_authority_preserved`
6. `consensus_integrity_preserved`
7. `finality_safety_preserved`
8. `evidence_trust_preserved`
9. `fund_flow_safe`
10. `external_fetch_surface_safe`
11. `liveness_preserved`
12. `behavioral_scope_matches_release`
13. `migration_safety_preserved`
14. `constitution_satisfied`

Every value must be an exact boolean. All fourteen `true` values produce
`APPROVE`; any false value produces `REJECT`. Missing or malformed output is a
retryable invalid result. There is no confidence threshold, score, majority
rule, percentage, prose authorization or partial approval.

## Evidence boundary

V2 captures evidence before semantic review. Leader and validators
independently retrieve and authenticate the immutable parent source, exact
frozen candidate bytes, CI envelope and optional or required security envelope.
They compare exact bytes, hashes, schema, issuer, IDs, target, parent hash,
candidate hash, policy fingerprint, freshness, expiry and required checks
before a complete snapshot is written.

`review_proposal` reads only the authenticated snapshot and frozen proposal
data. It performs zero live web fetches. The review prompt labels the
constitution, parent source, candidate source, CI evidence and security
evidence as untrusted data and instructs validators to ignore embedded
instructions, fake verdicts, JSON directives, comments and source prompt
injection. External security evidence is supporting data in OPTIONAL mode and
cannot replace the validators' own substantive decision.

`REQUIRED_INDEPENDENT` additionally requires a distinct security publisher and
a valid passing independent artifact before `EVIDENCE_READY`. `OPTIONAL` may
legitimately snapshot no security artifact and must never represent that
absence as an audit.

Consensus compares target, proposal ID, parent hash, candidate hash, policy
fingerprint, evidence identity, result kind, error class, decision and every
one of the fourteen booleans exactly. The result is not authorized until
finality and the target's exact installation attestation are both observed.
