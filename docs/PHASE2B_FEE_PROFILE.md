# Phase 2B fee-profile status — SentinelX V1 historical evidence

This is historical SentinelX V1 profiling evidence. SentinelX V2 has a new
contract layout and must not treat these measurements as authoritative.

Studio-dev is the official fee-reporting environment for this profiling pass:
`https://studio-dev.genlayer.com/api`, chain `61997`. The installed family is
GenLayer CLI `0.40.0-rc.3`, genlayer-js `2.0.0-rc.1`, genlayer-py
`0.19.0rc2`, and gltest `0.30.0rc2`.

The live policy reported fee-charging mode (`enabled: true`). The Python SDK's
generic estimator returned a complete `distribution` plus `feeValue`, and its
concrete `estimate_transaction_fees_for_write()` helper returned a complete
write quote. Gasless behavior is determined from the live estimate, never from
the network name.

The disposable run is labeled `NON_CANONICAL_PROFILE_ONLY`. It deployed the
exact governor and `protected_app_v1`, performed `set_protected_value`, and
required `Finalized` plus `FINISHED_WITH_RETURN` plus readback before accepting
each successful observation. The first target attempt failed because its
constructor address was encoded as a plain string; that finalized failed
transaction remains in the journal and was not rebroadcast. The corrected retry
used `CalldataAddress` and succeeded.

The complete disposable provenance is:

| Item | Value | Classification |
| --- | --- | --- |
| Profile governor deployment | `0x8239ee1d03e3b77ee3fe12171870d9a147e74c2f6883951fe687dab31e4a790d` | `NON_CANONICAL_PROFILE_ONLY` |
| Profile governor address | `0x23B6580934Daf74A58c0D7B423A1067eaB66C709` | `NON_CANONICAL_PROFILE_ONLY` |
| First profile target attempt | `0x27184ae71048d11d4677a278eded4b72c36859ec98b4818094897f697001e3fc` — `Finalized`, `FINISHED_WITH_ERROR` | `NON_CANONICAL_PROFILE_ONLY` · historical negative evidence |
| Corrected profile target deployment | `0x88aa3b7498c9d848c81c2b576013fd8d69f8f53ad070a04c3785d2c6062f0076` — `Finalized`, `FINISHED_WITH_RETURN` | `NON_CANONICAL_PROFILE_ONLY` |
| Profile target address | `0x7E14758f38926fef9E03e2Fd9D2C6575eB83607E` | `NON_CANONICAL_PROFILE_ONLY` |

Every item above is `NON_CANONICAL_PROFILE_ONLY` and is excluded from
production configuration.

The preserved artifacts are:

- `artifacts/v1/fee-profile.json` — measured Studio-dev deployment and
  `set_protected_value` observations with 1.25 headroom.
- `artifacts/v1/fee-profile-coverage.json` — observed and missing coverage.

The original transaction journal is not treated as a V2 artifact; the exact
transaction IDs and their separate stored status, lifecycle and execution
outcomes are preserved above as provenance. The failed first target attempt is
negative evidence only.

The profile is intentionally partial. Registration, governance review, repair,
reconciliation, timeout, confirmation, and protected installation methods were
not measured because no independent security publisher was available. No
security authority or security evidence was fabricated, and no canonical
SentinelX deployment was attempted. V2 uses fresh SDK fee estimation until a
new V2 profiling run is explicitly authorized.
