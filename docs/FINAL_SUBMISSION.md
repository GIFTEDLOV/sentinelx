# SentinelX canonical submission

Project: SentinelX  
Description: a GenLayer-governed release-security layer that authenticates
exact evidence, performs a zero-fetch semantic review, and verifies finalized
installation.

## Release

The canonical deployment is on Studionet, chain `61999`, at
`https://studio.genlayer.com/api`.

- Governor: `0xb28b8E7F8930b4bd7Ed8572dA7e51AA4ca9D7cA8`
- Protected target: `0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21`
- Production UI: <https://sentinelx-lac.vercel.app>
- Repository: <https://github.com/GIFTEDLOV/sentinelx>
- Source revision: `cfb25215497adeb41357196caa8c755a685b4cf2`
- Qualification head: `7dca629f7e413deaffad106a6ccad30164ac4ea7`
- Canonical deployment artifact head: `55596ade32f3f76069b356d901a284e24c338d80`
- Final hardening head: `76c8fb1db550b01c4ba2772f60a244ea1a9aea83`

The exact source hashes and toolchain are in
`deployments/studionet/v2.3/SOURCE_MANIFEST.json`. The canonical transaction
and provenance record is in
`deployments/studionet/v2.3/CANONICAL_DEPLOYMENT.json`.

## Security architecture

SentinelX binds a target policy to immutable parent and candidate source bytes,
stages exact evidence deterministically, captures only compact remote facts,
and constructs an authenticated snapshot from staged bytes. Semantic review
uses stored bytes and performs zero web fetches. Approval requires all fourteen
semantic fields to be true. The governor remains the sole upgrade authority;
the target validates its own installed state and emits the finalized
confirmation.

OPTIONAL security mode was used for this release. No external audit is claimed.

## Safe proof

Proposal `1` reached `VERIFIED` with candidate hash
`1073b34f141b9dc5ba689ef3d98293fd628e30695dbd9092a9c6ecaba3d8c27d`.
The semantic decision was `APPROVE`, the vector was `14/14 TRUE`, review-time
web fetches were `0`, and compact capture output was `827` bytes. Persistent
protected state, its value nonce, and governor authority were preserved. The
V2.3 release-note feature was read back successfully.

Key transactions:

- Governor deploy: `0xb05856ecf32315d5eb177242d63c58c0a2ffdf94dfd7df00bc9bcb56983bad31`
- Target deploy: `0x0e6ec21599ebe001e09068bcb45e41c8e4b0e6a51fe6aff6879403de654fe3c0`
- Registration parent: `0x9c37f3a2c5b42efe0c533002d8db2a91e18f273638f1d586e0e0f17935e4f851`
- Registration child: `0x7ec65c792d1e460f79b1af541d733c68f4b48b86e8459274095186f677a91d36`
- Proposal: `0x438d4cba1b96a3e12a8cc9d1dd958f80e896adf003eab90ed6aeec4ddd81cb60`
- Stage: `0xd2d1b44c4bd23241f4ee39214574b7f803fb754d9f6479f4ae501fa498b334e4`
- Capture: `0xf51008602f9a69cbc9f03cfc4f0292b55132727edc04fe2026ba47c5b0a026f5`
- Review: `0xa0d2b4fb481f05ea28a63a429136177e8985d49ed11f22abd14ea8e291d8740a`
- Execute: `0x86d62ebda5e27874cf93061aa584d1d38883d474077e409d9ed6b60a5e09bcc2`
- Install child: `0x7fd361524564047263c4e1340f27d9e512627209a73de66a2ce7b44753b57b03`
- Confirmation child: `0xbcbe5febcf11623ed7558d45fda71c06f66f26a2ef0c69a7334455a54021209f`

Every listed transaction finalized with `FINISHED_WITH_RETURN`.

## Negative proof and qualification

The unsafe candidate was tested only on a disposable qualified profile. It was
rejected, had thirteen false semantic fields, was not installed, and preserved
target state. The qualified 152 direct tests and 55/55 mutation suite remain
in the readiness and qualification artifacts; the profile addresses are
explicitly non-canonical.

## Reproduction

1. Verify the four source hashes against the source manifest.
2. Run the stable preflight, direct tests, semantic validation, mutation suite,
   frontend tests, typecheck, build, lint, and secret scan.
3. Read the canonical deployment manifest and immutable CI URL.
4. Read governor proposal `1`, its release history, target installed hash,
   protected value, value nonce, and upgrade governor on finalized state.
5. Open the production UI and inspect the canonical project and verified
   release views on Studionet.

The full live proof, staged digest, snapshot digest, CI evidence commit, and
readiness status are committed under `artifacts/studionet/v2.3/` and
`deployments/studionet/v2.3/`.

## Final hardening

The production console hardening record is in
[`docs/REVIEWER_HARDENING.md`](REVIEWER_HARDENING.md). It covers stable
transaction snapshots, local error containment, finalized chain-state labels,
evidence liveness and authority binding, proposal/target isolation, and
finality-safe retry behavior. The production browser route suite exercises the
canonical UI with fresh, valid, and corrupt local transaction storage.
