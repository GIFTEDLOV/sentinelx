# Integration tests

Phase 2A still does not deploy or run against Studio-dev. This directory is
reserved for a later explicitly authorized integration suite that will use the
pinned `studio_devnet` chain 61997, measured fee estimation, `distribution`,
`feeValue`, and finalized lifecycle reconciliation.

`scripts/build_fee_profile.py --dry-run` prints the supported profile command.
The checked-in `fee-profile.request.json` is a request manifest, not a fee
profile; no measured profile is present until representative writes produce
finalized observations.
