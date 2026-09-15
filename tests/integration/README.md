# Integration profiling

This directory is reserved for the explicitly authorized fee-reporting
profiling suite. The suite may use the installed `gltest` RC against the
official hosted Studio-dev environment at
`https://studio-dev.genlayer.com/api` (chain `61997`); every measured scenario
must be both `FINALIZED` and execution-successful.

The earlier Local Studio/Docker audit remains historical context only; it is
not a blocker for this pass because the official documentation permits a
fee-reporting Studio/network. Do not reinterpret Studio v0.123 as a
`--localnet-version` value.

`scripts/build_fee_profile.py --dry-run` prints the fail-closed profile
command. `fee-profile.request.json` is a request manifest, never a measured
profile. The disposable SDK runner and journal are the source for the current
partial profile; add scenarios only when their finalized receipts genuinely
exist.
