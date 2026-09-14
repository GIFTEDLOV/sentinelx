"""Small transaction-safety primitives for future Studio-dev write clients.

The module deliberately stops before broadcasting. A caller must perform its
own precondition read, call the SDK fee estimator, persist the returned hash
immediately after one broadcast, and reconcile that same hash through lifecycle
and contract-state reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class FeeEstimatingClient(Protocol):
    def estimate_transaction_fees(self, request: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class FeeAwareOptions:
    fees_distribution: Any
    fee_value: Any


def estimate_fee_aware_options(
    client: FeeEstimatingClient, request: dict[str, Any]
) -> FeeAwareOptions:
    """Return both v0.6 fee fields from the SDK estimator.

    Missing fields fail closed. No default fee, rebroadcast, or transaction
    hash is synthesized here.
    """
    estimate = client.estimate_transaction_fees(request)
    if "FeesDistribution" not in estimate or "feeValue" not in estimate:
        raise ValueError("v0.6 fee estimate must contain FeesDistribution and feeValue")
    return FeeAwareOptions(estimate["FeesDistribution"], estimate["feeValue"])


def validate_reconciled_result(
    *, lifecycle: str, execution_result: str, expected_state: bool
) -> None:
    """Enforce the three-part success proof for a consequential write."""
    if lifecycle != "FINALIZED":
        raise ValueError("ACCEPTED or non-final lifecycle is not sufficient")
    if execution_result != "SUCCESS":
        raise ValueError("finality without successful execution is not sufficient")
    if not expected_state:
        raise ValueError("successful execution without expected state is not sufficient")
