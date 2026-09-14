"""Fee-profile and transaction-safety primitives for Studio-dev v0.6 writes.

The SDK returns the v0.6 fields ``distribution`` and ``feeValue``.  This
module never invents either value and never retries a broadcast.  A caller
must perform its own precondition read, estimate from a measured profile, save
the returned hash immediately, and reconcile that same hash through lifecycle,
execution, and contract-state reads.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Protocol


class FeeEstimatingClient(Protocol):
    def estimate_transaction_fees(self, request: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class FeeAwareOptions:
    distribution: Any
    fee_value: Any

    @property
    def fees_distribution(self) -> Any:
        """Compatibility alias for callers that use the long SDK term."""
        return self.distribution

    def as_sdk_fees(self) -> dict[str, Any]:
        return {"distribution": self.distribution, "feeValue": self.fee_value}


def estimate_fee_aware_options(
    client: FeeEstimatingClient, request: dict[str, Any]
) -> FeeAwareOptions:
    """Return both v0.6 fee fields from the SDK estimator.

    Missing fields fail closed. No default fee, rebroadcast, or transaction
    hash is synthesized here.
    """
    estimate = client.estimate_transaction_fees(request)
    return fee_options_from_result(estimate)


def fee_options_from_result(estimate: dict[str, Any]) -> FeeAwareOptions:
    """Validate an already-returned live SDK estimate without changing it."""
    if "FeesDistribution" in estimate:
        raise ValueError("legacy FeesDistribution fee field is not accepted")
    if "distribution" not in estimate or "feeValue" not in estimate:
        raise ValueError("v0.6 fee estimate must contain distribution and feeValue")
    return FeeAwareOptions(estimate["distribution"], estimate["feeValue"])


PROFILE_FIELDS = (
    "leaderTimeunitsAllocation",
    "validatorTimeunitsAllocation",
    "executionBudgetPerRound",
    "totalMessageFees",
    "rotationsPerRound",
)


def _uint(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an unsigned integer")
    try:
        parsed = int(str(value), 10)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an unsigned integer") from error
    if parsed < 0:
        raise ValueError(f"{field} must be an unsigned integer")
    return parsed


def profile_entry_to_estimate_options(
    entry: dict[str, object], *, appeal_rounds: int
) -> dict[str, object]:
    """Convert one gltest observation to the current SDK estimator shape."""
    if appeal_rounds < 0:
        raise ValueError("appeal_rounds must be non-negative")
    missing = [field for field in PROFILE_FIELDS if field not in entry]
    if missing:
        raise ValueError(f"fee profile entry is missing: {', '.join(missing)}")
    rotations_per_round = _uint(entry["rotationsPerRound"], "rotationsPerRound")
    return {
        "leaderTimeunitsAllocation": _uint(
            entry["leaderTimeunitsAllocation"], "leaderTimeunitsAllocation"
        ),
        "validatorTimeunitsAllocation": _uint(
            entry["validatorTimeunitsAllocation"], "validatorTimeunitsAllocation"
        ),
        "appealRounds": appeal_rounds,
        "executionBudgetPerRound": _uint(
            entry["executionBudgetPerRound"], "executionBudgetPerRound"
        ),
        "totalMessageFees": _uint(entry["totalMessageFees"], "totalMessageFees"),
        "rotations": [rotations_per_round] * (appeal_rounds + 1),
    }


def load_fee_profile(
    path: Path,
    *,
    required_methods: tuple[str, ...],
    network: str = "studio_devnet",
    chain_id: int = 61997,
) -> dict[str, object]:
    """Load a measured gltest profile and reject incomplete/fake profiles."""
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load fee profile {path}: {error}") from error
    if not isinstance(profile, dict):
        raise ValueError("fee profile must be a JSON object")
    if profile.get("version") != 1 or profile.get("network") != network:
        raise ValueError("fee profile version/network does not match Studio-dev")
    if profile.get("chainId") != chain_id:
        raise ValueError("fee profile chain ID does not match Studio-dev")
    deploy = profile.get("deploy")
    methods = profile.get("methods")
    if not isinstance(deploy, dict) or not isinstance(methods, dict):
        raise ValueError("fee profile requires deploy and methods observations")
    profile_entry_to_estimate_options(deploy, appeal_rounds=0)
    for method in required_methods:
        entry = methods.get(method)
        if not isinstance(entry, dict):
            raise ValueError(f"fee profile has no measured observation for {method}")
        profile_entry_to_estimate_options(entry, appeal_rounds=0)
    return profile


def estimate_from_profile(
    client: FeeEstimatingClient,
    profile: dict[str, object],
    *,
    operation: str,
    appeal_rounds: int,
) -> FeeAwareOptions:
    """Ask the live SDK estimator using one measured profile observation."""
    raw_entry = profile.get("deploy") if operation == "deploy" else (
        profile.get("methods", {}).get(operation)  # type: ignore[union-attr]
        if isinstance(profile.get("methods"), dict) else None
    )
    if not isinstance(raw_entry, dict):
        raise ValueError(f"fee profile has no observation for {operation}")
    request = profile_entry_to_estimate_options(raw_entry, appeal_rounds=appeal_rounds)
    return estimate_fee_aware_options(client, request)


def validate_reconciled_result(
    *, lifecycle: str, execution_result: str, expected_state: bool
) -> None:
    """Enforce the three-part success proof for a consequential write."""
    if lifecycle.upper() != "FINALIZED":
        raise ValueError("ACCEPTED or non-final lifecycle is not sufficient")
    if execution_result != "FINISHED_WITH_RETURN":
        raise ValueError("finality without successful execution is not sufficient")
    if not expected_state:
        raise ValueError("successful execution without expected state is not sufficient")
