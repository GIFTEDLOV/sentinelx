# Integration profiling

This directory is reserved for the explicitly authorized Local Studio
profiling suite. The suite must use the installed `gltest` RC against the
official Docker-backed Localnet, not Direct Mode or GLSim, and every measured
scenario must be both `FINALIZED` and execution-successful.

The Phase 2C environment audit did not produce a runnable suite: the healthy
`v0.65.0` Compose stack reported chain `61999` (stable Studionet-era
configuration), while the required Localnet chain is `61127`. The attempted
`v0.123.0-rc.6` stack could not be started because its Hardhat image tag was
unpublished and its JSON-RPC container failed readiness with `missing field
extra_tld`. No profiling transaction or fee profile was created.

`scripts/build_fee_profile.py --dry-run` prints the fail-closed profile
command. `fee-profile.request.json` is a request manifest, never a measured
profile. Add integration tests only when the correct Local Studio RC is
verified and receipts expose measured fee accounting.
