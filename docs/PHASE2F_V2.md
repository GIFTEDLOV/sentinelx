# SentinelX V2 — pre-canonical architecture freeze

SentinelX V1 is the historical pre-canonical architecture recorded at git
commit `7e3b552c8b0471db0411206fdbc743dd12ef4e80`. It remains reachable and
is not rewritten. No V1 or V2 canonical governor or target has been deployed.

SentinelX V2 is the candidate for the first canonical Studio-dev deployment.
The intended network is `studio-dev`, RPC
`https://studio-dev.genlayer.com/api`, chain `61997`. This phase performs zero
chain writes and freezes source, tests and deployment gates only.

## Attestation policy

Every registered target stores an immutable bounded security-attestation mode:

- `OPTIONAL`: immutable parent/candidate source evidence, authenticated CI
  evidence and the GenLayer 14-field semantic review are required. No
  external audit is claimed when no security artifact is supplied. If an
  optional artifact is supplied, it is authenticated supporting data and does
  not replace validator judgment.
- `REQUIRED_INDEPENDENT`: security authority and prefix are required, the raw
  GitHub owner must differ from the source owner, and a valid independently
  published security artifact must bind target, parent hash, candidate hash,
  policy fingerprint and the configured passing verdict before readiness.

The required mode is never silently downgraded. Protocol fee quoting and the
application safety policy are separate concerns: SDK/network-default quotes
can permit a protocol submission, while SentinelX may keep high-consequence
canonical operations disabled until representative measured coverage exists.

## Evidence lifecycle

The V2 lifecycle is explicit:

`PROPOSED → capture_evidence → EVIDENCE_READY → review_proposal →
UPGRADE_QUEUED → VERIFIED`

Failed remote retrieval is retryable; invalid, stale or mismatched evidence is
repairable. Existing `REJECTED`, `EXPIRED`, `CANCELLED`, `EXECUTION_FAILED`
and reconciliation paths retain their specific meanings.

`capture_evidence` is the only phase that retrieves remote evidence. Leader and
validators independently fetch and authenticate the exact parent bytes,
candidate bytes, CI envelope and, when present or required, security envelope.
The candidate fetched from its immutable source must equal the exact frozen
proposal bytes. No partial snapshot is written.

The resulting `EvidenceSnapshotRecord` is proposal-bound, hash-authenticated,
schema-authenticated, write-once for its evidence identity, and readable
through bounded views. The evidence identity derives from proposal ID, target,
committed source hashes, evidence IDs and policy fingerprint; transport URLs
are provenance/recovery metadata and do not define identity. An exact-byte
mirror therefore does not become a different substantive artifact.

`review_proposal` requires `EVIDENCE_READY`, revalidates stored hashes and CI
bindings, and performs zero `gl.nondet.web.get` calls. Its semantic prompt
contains only authenticated stored snapshots, the constitution, release intent
and proposal bindings. Every external or code-derived value is delimited as
untrusted data, and embedded instructions, fake verdicts and prompt injection
are non-authoritative. The inspectable `get_review_web_fetch_count` view is
expected to remain zero.

## Semantic authorization

The exact fourteen fields remain the sole authorization vector, in the order
recorded in `docs/SEMANTIC_REVIEW.md`. Leader and validators must derive the
same complete vector. All fourteen exact booleans must be `true` for
`APPROVE`; any false, missing or malformed field rejects or retries as
appropriate. Confidence, prose, scores, majority rules and partial-pass
percentages are not authorization inputs.

## Deployment gate

`deployments/v2/SOURCE_MANIFEST.json` records source paths, byte counts,
SHA-256 hashes, Studio-dev network identity and the RC toolchain family.
`scripts/studio_dev_v2_deploy.py` defaults to read-only manifest verification.
Its future broadcast path rechecks source bytes immediately before estimation,
requires chain 61997, estimates fees freshly, persists a returned transaction
hash before polling, requires `Finalized` plus `FINISHED_WITH_RETURN`, and
requires contract-info and deployed-source parity checks. It is not run in
Phase 2F.

The historical V1 profile is preserved under `artifacts/v1/`. It is not a V2
fee profile. No V2 production addresses, profile addresses or external
security publisher are configured by this phase.
