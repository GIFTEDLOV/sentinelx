# Phase 2B fee-profile status

SentinelX does not currently contain a production `fee-profile.json`.

The installed `genlayer-test` 0.30.0rc2 package exposes the local `glsim`
process. A local instance was verified on `http://127.0.0.1:4017/api` with
chain ID 61997. Its fee configuration reports `enabled: false` and zero
Gen/time-unit, storage and receipt prices. Its finalized simulator receipts
therefore cannot measure the Studio-dev fee quantities needed for a production
profile; checking those zeros in would be unsafe.

The repository also has no representative integration transaction suite yet
(`gltest --collect-only tests/integration` collected zero tests), and Docker
Desktop is not running for a local Studio deployment. The fail-closed command
below remains the generation path once a compatible profiling environment and
legitimate finalized receipts are available:

```text
python scripts/build_fee_profile.py --run --allow-network-writes
```

It requires `SENTINELX_ALLOW_BROADCAST=1`, refuses to overwrite an existing
profile, and validates every required deployment and method observation before
leaving `fee-profile.json` behind. The current coverage request is recorded in
`fee-profile.request.json` and includes deploy, registration, proposal,
review, repair, retry, cancellation, expiry, reconciliation, timeout,
confirmation and protected installation paths.

No canonical Studio-dev write was used for profiling in Phase 2B.
