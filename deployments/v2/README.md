# SentinelX V2 deployment candidate

`SOURCE_MANIFEST.json` is the frozen source gate for the first canonical
SentinelX deployment candidate. It binds the four contract paths, exact byte
counts and SHA-256 hashes to Studio-dev chain `61997` and the documented RC
toolchain family.

No canonical deployment has occurred. `scripts/studio_dev_v2_deploy.py` is
read-only by default and its broadcast path is intentionally operator-gated.
Before a future deployment it must recompute every source byte, require the
manifest/network match, estimate fees freshly, persist the returned hash before
polling, and prove `Finalized` + `FINISHED_WITH_RETURN`, contract-info schema,
and deployed source parity.
