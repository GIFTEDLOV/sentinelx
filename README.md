<p align="center">
  <img src="frontend/app/icon.svg" alt="SentinelX mark" width="72" />
</p>

<h1 align="center">SentinelX</h1>

<p align="center"><strong>Ship code. Not trust assumptions.</strong></p>

<p align="center">Semantic release security for GenLayer Intelligent Contracts — exact source binding, authenticated evidence, 14-field validator review, finalized installation, and auditable release history.</p>

<p align="center">
  <a href="https://sentinelx-lac.vercel.app">Live App</a> ·
  <a href="docs/ARCHITECTURE.md">Architecture</a> ·
  <a href="deployments/studionet/v2.3/CANONICAL_DEPLOYMENT.json">Deployment</a> ·
  <a href="docs/REVIEWER_HARDENING.md">Security Hardening</a> ·
  <a href="docs/FINAL_SUBMISSION.md">Submission Proof</a>
</p>

## What SentinelX is

SentinelX is a GenLayer-governed release-security layer for protected Intelligent Contracts. It places authenticated evidence and bounded semantic consensus between an upgrade proposal and production code.

A release cannot become verified merely because an owner proposes it. SentinelX freezes the candidate bytes, binds the proposal to the exact parent state and policy, authenticates immutable evidence, asks validators to evaluate fourteen explicit safety properties, installs only an approved candidate, and records the release as `VERIFIED` only after finalized target-originated confirmation.

The boundary is deliberate: validators make the narrow semantic judgment; deterministic contract logic controls authorization, evidence identity, proposal state, installation, finality, replay protection, and release history.

## SentinelX at a glance

| Area | Canonical implementation |
| --- | --- |
| Network | GenLayer Studionet |
| Chain ID | `61999` |
| RPC | `https://studio.genlayer.com/api` |
| Canonical governor | `0xb28b8E7F8930b4bd7Ed8572dA7e51AA4ca9D7cA8` |
| Canonical protected target | `0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21` |
| Safe installed SHA-256 | `1073b34f141b9dc5ba689ef3d98293fd628e30695dbd9092a9c6ecaba3d8c27d` |
| Evidence model | deterministic exact-byte staging → compact remote attestation → authenticated snapshot |
| Judgment model | 14 explicit boolean safety properties; all 14 must be `true` |
| Canonical safe result | `APPROVE → VERIFIED` |
| Qualified unsafe result | `REJECTED` · not installed |
| Review-time web fetches | `0` |
| Transaction safety | persist hash before polling; reconcile the same hash; never blind-rebroadcast |
| Frontend | Next.js 16 · React 19 · TypeScript · GenLayerJS 1.1.8 |
| Production | [sentinelx-lac.vercel.app](https://sentinelx-lac.vercel.app) |

## Contents

- [Why SentinelX](#why-sentinelx)
- [Why GenLayer](#why-genlayer)
- [Core design principles](#core-design-principles)
- [How SentinelX works](#how-sentinelx-works)
- [Release lifecycle](#release-lifecycle)
- [The 14-field safety matrix](#the-14-field-safety-matrix)
- [Evidence model](#evidence-model)
- [Trust model](#trust-model)
- [Transaction safety](#transaction-safety)
- [Canonical deployment](#canonical-deployment)
- [End-to-end verified proof](#end-to-end-verified-proof)
- [Unsafe candidate proof](#unsafe-candidate-proof)
- [Security properties](#security-properties)
- [Application](#application)
- [Technology](#technology)
- [Verification and testing](#verification-and-testing)
- [Repository structure](#repository-structure)
- [Local development](#local-development)
- [Verify SentinelX in 5 minutes](#verify-sentinelx-in-5-minutes)
- [Limitations](#limitations)
- [Status](#status)

## Why SentinelX

Upgrading an Intelligent Contract is not only a bytecode problem. A release can preserve syntax while changing authority, weakening evidence guarantees, altering storage assumptions, introducing hidden external dependencies, or expanding privileged behavior.

Traditional upgrade controls answer questions like “who may upgrade?” SentinelX adds a different gate:

> Does this exact candidate preserve the security and behavioral assumptions this protected contract committed to?

That question requires interpretation across source code, release intent, CI evidence, policy, storage layout, authority, liveness, finality, and external-fetch behavior. SentinelX makes the judgment explicit, bounded, reproducible, and tied to deterministic on-chain consequences.

## Why GenLayer

A deterministic contract can hash bytes, enforce deadlines, authorize callers, and manage proposal state. It cannot by itself perform a bounded semantic comparison of two non-trivial source versions and determine whether authority, behavior, liveness, and release intent still match.

GenLayer provides the validator-backed boundary for that semantic question:

~~~text
freeze exact candidate bytes
    → authenticate proposal-bound evidence
    → construct immutable snapshot
    → validator semantic review
    → require 14/14 true
    → deterministic installation authorization
    → finalized target confirmation
    → VERIFIED release
~~~

Consensus does not authenticate evidence by itself. SentinelX authenticates the evidence first, then gives validators a narrow decision surface.

## Core design principles

| Principle | SentinelX implementation |
| --- | --- |
| Authenticate before adjudicating | Exact parent/CI/security bytes are staged deterministically before remote provenance is attested. |
| Frozen candidate identity | Candidate bytes and SHA-256 are fixed at proposal creation and cannot be repaired into different code. |
| Narrow validator authority | Validators return exactly fourteen booleans; they do not choose targets, hashes, authorities, or installation consequences. |
| All-true approval | One false field is enough to reject the candidate. There is no fuzzy confidence threshold. |
| Zero-fetch review | Semantic review consumes the authenticated stored snapshot and performs zero web fetches. |
| Fail closed | Missing, stale, malformed, mismatched, or unavailable evidence cannot become approval. |
| Replay resistance | Evidence identifiers are global replay tokens and cannot be rebound across targets or evidence kinds. |
| Finality before verification | `UPGRADE_QUEUED` is not `VERIFIED`; installation and target confirmation are separate steps. |
| No owner bypass | The protected target accepts upgrades only from the SentinelX governor. |
| Safe recovery | Target-originated confirmation retry uses the target’s own installed proposal/hash; the owner cannot supply an arbitrary hash. |
| No blind rebroadcast | Ambiguous polling preserves the same transaction hash for reconciliation. |
| Honest UI state | `PROPOSED`, `EVIDENCE_STAGED`, `EVIDENCE_READY`, `UPGRADE_QUEUED`, `VERIFIED`, and `REJECTED` remain visually distinct. |

## How SentinelX works

~~~mermaid
flowchart LR
    O[Target owner] --> P[Release proposal]
    P --> F[Freeze exact candidate bytes + hash]
    F --> S[Deterministic evidence staging]
    E[Immutable source + CI evidence] --> A[Independent remote attestation]
    S --> A
    A --> X[Authenticated snapshot]
    X --> R[14-field semantic review]
    R --> C[GenLayer consensus]
    C -->|14/14 true| Q[UPGRADE_QUEUED]
    C -->|any false| J[REJECTED]
    Q --> I[Governor-authorized installation]
    I --> T[Protected target]
    T -->|finalized target confirmation| V[VERIFIED]
~~~

The production frontend reads the canonical governor and target on Studionet. Disposable qualification addresses are kept only as historical proof and are never substituted into active production configuration.

## Release lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> PROPOSED: create_proposal
    PROPOSED --> EVIDENCE_STAGED: stage_evidence
    EVIDENCE_STAGED --> EVIDENCE_READY: capture_evidence
    EVIDENCE_READY --> UPGRADE_QUEUED: 14/14 APPROVE
    EVIDENCE_READY --> REJECTED: any semantic field false
    UPGRADE_QUEUED --> VERIFIED: finalized install + target confirmation
    PROPOSED --> EVIDENCE_REPAIR_REQUIRED: authenticated evidence defect
    PROPOSED --> EVIDENCE_RETRY_REQUIRED: transient evidence failure
    EVIDENCE_READY --> REVIEW_RETRY_REQUIRED: retryable review failure
    PROPOSED --> CANCELLED: owner cancellation
    PROPOSED --> EXPIRED: deadline
    UPGRADE_QUEUED --> EXECUTION_FAILED: terminal execution failure
~~~

The application does not collapse these states into a generic “reviewed” label. An unassessed proposal is not consensus-cleared; an approved proposal is not installed; and an installed candidate is not canonical until the governor records `VERIFIED`.

## The 14-field safety matrix

A candidate must pass every field:

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

The canonical safe candidate returned **14/14 TRUE**. The qualified unsafe candidate returned **13 false fields** and was rejected.

## Evidence model

SentinelX separates deterministic evidence bytes from nondeterministic provenance checks:

~~~text
immutable source / CI artifact
    → deterministic exact-byte staging
    → proposal-bound hashes + lengths
    → independent remote retrieval
    → compact attestation facts only
    → deterministic comparison against staged bytes
    → write-once authenticated snapshot
    → zero-fetch semantic review
~~~

The compact remote result is intentionally small. In the canonical release it was **827 bytes**. Bulk source or evidence bytes do not cross the nondeterministic receipt boundary.

The evidence identity binds the proposal, target, parent hash, candidate hash, evidence IDs, and policy fingerprint. Transport can be repaired with an exact-byte mirror, but identity cannot silently change.

## Trust model

SentinelX separates responsibilities:

1. The owner may propose a release, but cannot install it directly.
2. The governor freezes the proposal and enforces the active policy.
3. Exact evidence bytes are staged deterministically.
4. Validators independently attest immutable remote artifacts.
5. The contract constructs a write-once authenticated snapshot.
6. Validators return the bounded 14-field semantic vector from stored snapshot data.
7. Deterministic contract logic turns only 14/14 TRUE into upgrade authorization.
8. The protected target re-checks live governor authorization before replacing code.
9. The target confirms installation back to the governor only after finalized installation.
10. The frontend reads finalized chain state; it is not the source of truth.

External security evidence is policy-controlled: `OPTIONAL` or `REQUIRED_INDEPENDENT`. The canonical release uses `OPTIONAL`, so no external audit is claimed.

## Transaction safety

Every write follows the same operational discipline:

~~~text
PRECONDITION READ
    → FEE CHECK
    → BROADCAST ONCE
    → PERSIST HASH
    → TRACK SAME HASH
    → FINALIZED
    → EXECUTION RESULT
    → EXPECTED STATE READBACK
~~~

A finalized transaction is accepted as successful only when execution finished successfully and the expected state consequence is present. Polling failure never authorizes a replacement transaction.

The hardened frontend transaction store keeps distinct hashes even when operation names repeat, tolerates corrupt or old local storage, and resumes ambiguous transactions by the same hash.

## Canonical deployment

| Field | Value |
| --- | --- |
| Network | GenLayer Studionet |
| Chain ID | `61999` |
| RPC | `https://studio.genlayer.com/api` |
| Governor | `0xb28b8E7F8930b4bd7Ed8572dA7e51AA4ca9D7cA8` |
| Protected target | `0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21` |
| Governor deploy tx | `0xb05856ecf32315d5eb177242d63c58c0a2ffdf94dfd7df00bc9bcb56983bad31` |
| Target deploy tx | `0x0e6ec21599ebe001e09068bcb45e41c8e4b0e6a51fe6aff6879403de654fe3c0` |
| Policy fingerprint | `014cc4342eae61cf2d08907e92f05fd134c9d71f33a809519bebe7bcce26118e` |
| Safe candidate SHA-256 | `1073b34f141b9dc5ba689ef3d98293fd628e30695dbd9092a9c6ecaba3d8c27d` |
| Source revision | `cfb25215497adeb41357196caa8c755a685b4cf2` |
| Qualification head | `7dca629f7e413deaffad106a6ccad30164ac4ea7` |
| Canonical deployment artifact head | `55596ade32f3f76069b356d901a284e24c338d80` |
| Current public repository head | see `main` |

The exact machine-readable deployment proof is retained in [`CANONICAL_DEPLOYMENT.json`](deployments/studionet/v2.3/CANONICAL_DEPLOYMENT.json).

## End-to-end verified proof

Canonical proposal **1** completed the full release path:

| Step | Result | Transaction |
| --- | --- | --- |
| Proposal | candidate frozen and active | `0x438d4cba1b96a3e12a8cc9d1dd958f80e896adf003eab90ed6aeec4ddd81cb60` |
| Stage | exact evidence bytes staged; not yet ready | `0xd2d1b44c4bd23241f4ee39214574b7f803fb754d9f6479f4ae501fa498b334e4` |
| Capture | authenticated snapshot created; 827-byte compact result | `0xf51008602f9a69cbc9f03cfc4f0292b55132727edc04fe2026ba47c5b0a026f5` |
| Review | `APPROVE`; 14/14 TRUE; zero review-time fetches | `0xa0d2b4fb481f05ea28a63a429136177e8985d49ed11f22abd14ea8e291d8740a` |
| Execute | finalized upgrade authorization | `0x86d62ebda5e27874cf93061aa584d1d38883d474077e409d9ed6b60a5e09bcc2` |
| Install child | exact safe candidate installed | `0x7fd361524564047263c4e1340f27d9e512627209a73de66a2ce7b44753b57b03` |
| Confirmation child | governor recorded installation | `0xbcbe5febcf11623ed7558d45fda71c06f66f26a2ef0c69a7334455a54021209f` |
| Final state | `VERIFIED`; state + nonce + authority preserved | — |

Every listed canonical transaction finalized with `FINISHED_WITH_RETURN`.

The final installed hash is:

~~~text
1073b34f141b9dc5ba689ef3d98293fd628e30695dbd9092a9c6ecaba3d8c27d
~~~

Persistent protected state, value nonce, and governor upgrade authority were preserved, and the safe V2.3 release-note feature was verified after installation.

## Unsafe candidate proof

The deliberately unsafe candidate was tested only in a disposable qualification environment.

| Property | Result |
| --- | --- |
| Decision | `REJECTED` |
| False semantic fields | 13 / 14 |
| Installed | NO |
| Target state preserved | YES |
| Upgrade authority preserved | YES |

The unsafe candidate is not deployed to the canonical target. Its role is adversarial proof that the semantic gate distinguishes a security-preserving release from a candidate containing authority, storage, value-flow, behavior, and liveness violations.

## Security properties

| Property | Status |
| --- | --- |
| Candidate bytes are frozen before review | PROVEN |
| Parent/candidate hashes are proposal-bound | PROVEN |
| Evidence issuer, target, kind, ID, policy and timestamps are authenticated | PROVEN |
| Evidence IDs cannot be replayed across targets or kinds | TESTED |
| Staged evidence alone cannot become reviewable | PROVEN |
| Remote capture cannot replace staged bytes | PROVEN |
| Snapshot is write-once | PROVEN |
| Semantic review performs zero web fetches | LIVE DEMONSTRATED |
| All fourteen fields are required for approval | LIVE DEMONSTRATED |
| Owner cannot directly install an upgrade | PROVEN |
| Rejected candidate cannot execute | TESTED |
| Finalized installation is distinct from semantic approval | LIVE DEMONSTRATED |
| Target-originated recovery cannot accept an owner-supplied hash | TESTED |
| Ambiguous transaction polling does not trigger blind rebroadcast | TESTED |
| Canonical source/deployment parity | LIVE DEMONSTRATED |
| Production UI distinguishes unassessed, queued, rejected and verified state | BROWSER TESTED |

More detail is in [`docs/REVIEWER_HARDENING.md`](docs/REVIEWER_HARDENING.md) and [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Application

The production console is a read-through interface over the canonical Studionet governor and target.

It exposes:

- protected contract inventory
- target policy and Release Constitution
- release history
- proposal/evidence state
- 14-field semantic review
- consensus/finality state
- canonical transaction history
- proof and security views
- wallet-aware write flows with same-hash reconciliation
- explicit loading, empty, degraded, rejected, queued and verified states

Production browser hardening includes **19 E2E route/storage cases** with no hydration or console errors in the final release.

## Technology

- Python GenLayer Intelligent Contracts
- Studionet `61999`
- `py-genlayer` pinned stable runner
- `genlayer-py 0.18.0`
- `genlayer-test 0.29.2`
- `genlayer-js 1.1.8`
- Next.js 16
- React 19
- TypeScript
- TanStack Query
- Vercel production deployment

## Verification and testing

The final hardened baseline is:

| Gate | Result |
| --- | --- |
| Direct contract tests | **152 PASS** |
| Mutation suite | **55/55 killed · 0 survivors** |
| Frontend tests | **24 PASS** |
| Browser E2E | **19 PASS** |
| Static lint | PASS |
| Semantic validation | PASS |
| Studionet preflight | PASS |
| Typecheck | PASS |
| Production build | PASS |
| Frontend lint | PASS |
| Secret scan | PASS |
| Release-integrity gate | PASS |
| Canonical source parity | PASS |

Useful local checks:

~~~powershell
python -m pytest tests/direct -q
python scripts/studionet_preflight.py
python scripts/validate_studionet_v23_semantics.py
python scripts/v2_mutation_runner.py
cd frontend
npm test
npm run typecheck
npm run build
npm run lint
~~~

The final hardening pass fixed a real production React `useSyncExternalStore` snapshot bug, added stable transaction-store snapshots and local error containment, expanded frontend/browser regression coverage, and did **not** modify or redeploy the canonical contract sources.

## Repository structure

~~~text
contracts/
  sentinelx_governor.py          canonical release governor
  protected_app_v1.py            baseline protected target
  protected_app_v2_safe.py       qualified safe candidate
  protected_app_v2_unsafe.py     adversarial unsafe candidate

frontend/
  app/                            Next.js routes
  components/                     console UI
  lib/genlayer/                   canonical reads, writes, fees, lifecycle tracking

tests/direct/                     deterministic contract/security regression suite
scripts/                          preflight, semantic, mutation and release checks
deployments/studionet/v2.3/      source, fee, readiness and canonical manifests
artifacts/studionet/v2.3/        qualification proof artifacts
docs/ARCHITECTURE.md              architecture and trust boundaries
docs/REVIEWER_HARDENING.md        reviewer-focused hardening evidence
docs/FINAL_SUBMISSION.md          canonical submission proof
docs/THREAT_MODEL.md              explicit threat model
~~~

## Local development

Requirements: Node 20.9+ / Node 24 recommended, npm, Python with the pinned stable GenLayer dependencies.

~~~powershell
git clone https://github.com/GIFTEDLOV/sentinelx
cd sentinelx/frontend
npm install
npm run dev
~~~

The frontend defaults to Studionet and reads canonical chain state. Production preview fixtures are disabled.

## Verify SentinelX in 5 minutes

1. Clone [`GIFTEDLOV/sentinelx`](https://github.com/GIFTEDLOV/sentinelx).
2. Open [`deployments/studionet/v2.3/CANONICAL_DEPLOYMENT.json`](deployments/studionet/v2.3/CANONICAL_DEPLOYMENT.json).
3. Confirm the canonical governor is `0xb28b8E7F8930b4bd7Ed8572dA7e51AA4ca9D7cA8` and target is `0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21`.
4. Verify proposal `1` is `VERIFIED`, review is `14/14 TRUE`, and installed SHA matches the safe candidate.
5. Run the direct, mutation, frontend and release-integrity checks.
6. Open [sentinelx-lac.vercel.app](https://sentinelx-lac.vercel.app) and inspect the canonical project/release views.
7. Read [`docs/REVIEWER_HARDENING.md`](docs/REVIEWER_HARDENING.md) for evidence-liveness, authority-binding, replay, object-isolation, finality, and transaction-safety coverage.

## Limitations

- The canonical release uses `OPTIONAL` external security attestation; no external audit is claimed.
- The unsafe candidate proof was intentionally run on a disposable qualification target, not the canonical production target.
- Historical Studio-dev and earlier V2/V2.1/V2.2 artifacts remain in the repository for engineering provenance but are not active production configuration.
- SentinelX proves the implemented release-governance invariants; it does not claim to prove every possible semantic property of arbitrary software.

## Status

SentinelX V2.3 is canonically deployed on GenLayer Studionet with a verified safe release, an independently qualified rejected unsafe release, source/deployment parity, hardened production UI, and auditable transaction/evidence records.

**Live app:** [sentinelx-lac.vercel.app](https://sentinelx-lac.vercel.app)

**Canonical governor:** `0xb28b8E7F8930b4bd7Ed8572dA7e51AA4ca9D7cA8`

**Canonical target:** `0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21`
