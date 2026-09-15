# Phase 2A tooling status — V1 historical tooling

The Phase 2A contract assumptions are retained for V1 provenance. Phase 2F
defines the pre-canonical V2 architecture and supersedes the universal
security-attestation requirement.

SentinelX's canonical lifecycle remains reserved for an explicitly authorized
Studio-dev run. The configured network is `studio-dev` at
`https://studio-dev.genlayer.com/api`, chain ID `61997`, using the pinned RC
family in `requirements.txt` and GenLayer CLI `0.40.0-rc.3`.

The public source anchor is `GIFTEDLOV/sentinelx`. The public CI authority is
the separate repository `GIFTEDLOV/sentinelx-ci`; its workflow checks out exact
source commits, runs the deterministic gates, and uploads a CI envelope for
authorized publication review. It does not publish security evidence.

The V1 governor required three distinct authority strings and three distinct
canonical raw-GitHub prefixes, with a different raw GitHub security owner. V2
replaces that universal prerequisite with an immutable `OPTIONAL` or
`REQUIRED_INDEPENDENT` target policy. The stronger distinct-owner rules remain
enforced in `REQUIRED_INDEPENDENT` mode.

`scripts/build_fee_profile.py --from-journal` is historical profiling tooling;
new output is isolated under `artifacts/v2/` and must be measured against V2.
The preserved V1 profile is under `artifacts/v1/` and is not authoritative for
V2.

`scripts/studio_dev_lifecycle.py` contains the write order, live SDK fee quote,
single-broadcast journal reservation, immediate returned-hash persistence,
same-hash reconciliation, expected final-state read, child tracking, and
decision-bound v0.6 `Finalize` handling. The canonical runner intentionally
requires its measured profile as an application safety policy; this does not
mean the Studio SDK cannot quote an unprofiled development write.

`scripts/build_security_review_packet.py` prepares exact parent/candidate bytes,
SHA-256 values, a semantic diff, the constitution, release intent, and the
required security envelope schema. It produces no verdict or security
evidence. `scripts/inject_security_authority.py` later accepts only a supplied
canonical raw-GitHub prefix owned by a different owner.

No canonical chain write, target registration, or security evidence is claimed
by this phase.
