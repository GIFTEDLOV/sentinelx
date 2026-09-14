# Semantic review contract

The authorization-driving safety vector has exactly 14 fields, in this order:

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

The decision rule is exact: all 14 values must be booleans and all must be
`True` for `APPROVE`. Any missing, non-boolean, or false value produces
`REJECT` or a retryable review error as appropriate. There is no confidence
threshold, fuzzy percentage, majority rule, score, or natural-language field
in the authorization path.

Before semantic adjudication, both leader and validators independently fetch
the authenticated parent source, candidate source, CI evidence, and security
evidence. Each independently verifies immutable URLs, exact bytes and hashes,
publishers, evidence IDs, target, parent/candidate hashes, policy fingerprint,
evidence-set hash, freshness, expiration, and the required CI/security gates.
They then independently compare parent and candidate against the constitution.

Consensus compares target, proposal ID, parent hash, candidate hash, policy
fingerprint, evidence-set hash, result kind, error class, decision, and every
one of the 14 booleans exactly. Reasoning text is not compared and cannot
authorize a release.

This design puts only irreducibly semantic comparison inside nondeterminism.
Infrastructure failure maps to `REVIEW_RETRY_REQUIRED`; authenticated evidence
defects map to `EVIDENCE_REPAIR_REQUIRED`; semantic rejection maps to
`REJECTED`.
