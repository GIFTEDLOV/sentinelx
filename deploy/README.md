# Deployment placeholder

No deployment is performed in Phase 1. When implemented, deployment scripts must use the explicit `studio-dev` profile and fee-aware v0.6 parameters (`FeesDistribution` and `feeValue`). They must never blind-rebroadcast after an ambiguous timeout.
Deployment is intentionally not implemented in Phase 1.

When Phase 2 begins, use the Studio-dev network in `gltest.config.yaml`, the
fee-aware helper in `scripts/fee_aware_transaction.py`, and the following
write lifecycle:

`PRECONDITION READ → ESTIMATE FEES → BROADCAST ONCE → PERSIST HASH →
RECONCILE SAME HASH → CHECK FINALITY/LIFECYCLE → CHECK EXECUTION RESULT →
READ EXPECTED STATE`.

The v0.6 fee request must include both `FeesDistribution` and `feeValue` from
the estimator. An `ACCEPTED` or `FINALIZED` label alone is not a successful
execution proof. No deployment address or transaction hash is recorded here.
