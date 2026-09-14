# Phase 2A tooling status

SentinelX is prepared for a later, explicitly authorized Studio-dev lifecycle
run. The configured network is `studio-dev` at
`https://studio-dev.genlayer.com/api`, chain ID `61997`, using the pinned RC
family in `requirements.txt` and GenLayer CLI `0.40.0-rc.3`.

The public source anchor is `GIFTEDLOV/sentinelx`. The public CI authority is
the separate repository `GIFTEDLOV/sentinelx-ci`; its workflow checks out exact
source commits, runs the deterministic gates, and uploads a CI envelope for
authorized publication review. It does not publish security evidence.

The governor requires three distinct authority strings and three distinct
canonical raw-GitHub prefixes. It additionally requires the raw GitHub owner
of the security prefix to differ from the source owner. Therefore a legitimate
independent security publisher is still required before target registration.

`scripts/build_fee_profile.py` refuses to create a profile without finalized
observations for deployment and every required lifecycle method. The tracked
`fee-profile.request.json` is only the coverage manifest; no guessed or empty
fee profile is checked in.

`scripts/studio_dev_lifecycle.py` contains the write order, live SDK fee quote,
single-broadcast journal reservation, immediate returned-hash persistence,
same-hash reconciliation, expected final-state read, child tracking, and
decision-bound v0.6 `Finalize` handling. Writes require both `--broadcast` and
`SENTINELX_ALLOW_BROADCAST=1`, plus a measured fee profile.

`scripts/build_security_review_packet.py` prepares exact parent/candidate bytes,
SHA-256 values, a semantic diff, the constitution, release intent, and the
required security envelope schema. It produces no verdict or security
evidence. `scripts/inject_security_authority.py` later accepts only a supplied
canonical raw-GitHub prefix owned by a different owner.

No chain write, deployment, target registration, security evidence, or frontend
implementation is claimed by this phase.
