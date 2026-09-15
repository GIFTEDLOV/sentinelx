"""Disposable Studio-dev fee profiling run using genlayer-py 0.19 RC.

This runner deploys the exact governor and protected v1 sources, performs one
ordinary target write, and records every returned hash before polling. It does
not register a target or make any security-publisher claim. The resulting
journal is the only source accepted by ``build_fee_profile.py --from-journal``.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RPC = "https://studio-dev.genlayer.com/api"
NETWORK = "studio-dev"
CHAIN_ID = 61997
JOURNAL = ROOT / "artifacts" / "studio-dev-profile-transactions.json"
GOVERNOR_SOURCE = ROOT / "contracts" / "sentinelx_governor.py"
TARGET_SOURCE = ROOT / "contracts" / "protected_app_v1.py"
LABEL = "NON_CANONICAL_PROFILE_ONLY"


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if hasattr(value, "value"):
        return _safe(value.value)
    return value


def _hash_text(value: Any) -> str:
    text = value.hex() if isinstance(value, bytes) else str(value)
    if not text.startswith("0x"):
        text = "0x" + text
    if len(text) != 66 or any(char not in "0123456789abcdefABCDEF" for char in text[2:]):
        raise ValueError("SDK returned an invalid 32-byte transaction hash")
    return text.lower()


def _journal() -> Any:
    from scripts.transaction_journal import TransactionJournal

    return TransactionJournal(JOURNAL)


def _operation_for_retry(journal: Any, base: str) -> str:
    """Choose a new journal key only after a prior attempt is finalized failed."""
    operations = journal.load()["operations"]
    current = operations.get(base)
    if not isinstance(current, dict) or current.get("state") == "FINALIZED_EXECUTED":
        return base
    index = 1
    while f"{base}.retry{index}" in operations:
        index += 1
    return f"{base}.retry{index}"


def _client() -> tuple[Any, Any]:
    from eth_account import Account
    from genlayer_py import create_client
    from genlayer_py.chains import studio_devnet

    if studio_devnet.id != CHAIN_ID or studio_devnet.rpc_urls["default"]["http"][0] != RPC:
        raise RuntimeError("installed genlayer-py chain is not Studio-dev 61997")
    key = os.environ.get("SENTINELX_PRIVATE_KEY")
    if not key:
        raise RuntimeError("SENTINELX_PRIVATE_KEY is required for disposable profiling writes")
    account = Account.from_key(key)
    return create_client(chain=studio_devnet, account=account), account


def _precondition(client: Any, account: Any) -> dict[str, Any]:
    address = client.w3.to_checksum_address(account.address)
    latest = int(client.get_current_nonce(address, "latest"))
    pending = int(client.get_transaction_count(address, "pending"))
    balance = int(client.get_balance(address, "latest"))
    if latest != pending:
        raise RuntimeError(f"account has unknown pending activity: latest={latest}, pending={pending}")
    return {"address": address, "latest_nonce": latest, "pending_nonce": pending, "balance_wei": balance}


def _require_complete_estimate(estimate: dict[str, Any]) -> dict[str, Any]:
    if "distribution" not in estimate or "feeValue" not in estimate:
        raise ValueError("SDK fee estimate must contain distribution and feeValue")
    # Keep the SDK's complete quote intact, including messageAllocations and
    # any observation metadata returned by the Studio estimator.
    return estimate


def _lifecycle(client: Any, tx_hash: str) -> dict[str, Any]:
    value = client.get_transaction_lifecycle(tx_hash)
    return {
        "stored_status": str(getattr(value.get("stored_status_name"), "value", value.get("stored_status_name"))),
        "projected_status": str(getattr(value.get("projected_status_name"), "value", value.get("projected_status_name"))),
        "resolution_action": str(getattr(value.get("resolution_action_name"), "value", value.get("resolution_action_name"))),
        "decision_id": value.get("decision_id"),
        "decision_active": bool(value.get("decision_active")),
        "evaluated_at": value.get("evaluated_at"),
    }


def _execution_result(receipt: dict[str, Any]) -> Any:
    return (receipt.get("tx_execution_result_name")
            or receipt.get("txExecutionResultName")
            or receipt.get("execution_result")
            or receipt.get("executionResult"))


def _contract_address(receipt: dict[str, Any]) -> Any:
    return (receipt.get("contract_address")
            or receipt.get("contractAddress")
            or receipt.get("recipient"))


def _wait_for_stable_final_receipt(client: Any, tx_hash: str) -> tuple[dict[str, Any], dict[str, Any], Any]:
    """Require two matching finalized reads before accepting execution."""
    previous: tuple[str, str] | None = None
    last: tuple[dict[str, Any], dict[str, Any], Any] | None = None
    for attempt in range(12):
        receipt = client.wait_for_transaction_receipt(
            tx_hash, wait_until="finalized", full_transaction=True,
        )
        receipt_json = _safe(receipt)
        lifecycle = _lifecycle(client, tx_hash)
        execution = _execution_result(receipt_json)
        current = (str(lifecycle.get("stored_status")), str(execution))
        last = (receipt_json, lifecycle, execution)
        if current == previous and current == ("Finalized", "FINISHED_WITH_RETURN"):
            return last
        previous = current
        if attempt < 11:
            time.sleep(2)
    if last is None:
        raise RuntimeError("Studio returned no receipt")
    return last


def _submit_and_finalize(
    *, client: Any, account: Any, journal: Any, operation: str, fee_observation_kind: str,
    method: str | None = None, address: str | None = None, args: list[Any] | None = None,
    code: bytes | None = None, contract_name: str | None = None,
    read_address: str | None = None, read_method: str | None = None,
) -> dict[str, Any]:
    existing = journal.load()["operations"].get(operation)
    if isinstance(existing, dict) and existing.get("tx_hash"):
        # A parser or polling failure must resume the persisted hash, never
        # reserve or broadcast a replacement transaction.
        tx_hash = _hash_text(existing["tx_hash"])
        estimate = existing.get("estimate") or {}
    else:
        _precondition(client, account)
        if code is not None:
            estimate = client.estimate_transaction_fees()
            fees = _require_complete_estimate(estimate)
        else:
            if address is None or method is None:
                raise ValueError("write address and method are required")
            estimate = client.estimate_transaction_fees_for_write(
                client.w3.to_checksum_address(address), method, account=account,
                args=args or [],
            )
            fees = _require_complete_estimate(estimate)

        journal.reserve_broadcast(
            operation, network=NETWORK, rpc=RPC, chain_id=CHAIN_ID,
            label=LABEL, fee_observation_kind=fee_observation_kind,
            contract_name=contract_name, method=method,
            estimate=_safe(estimate),
        )
        try:
            if code is not None:
                returned = client.deploy_contract(
                    code=code, account=account, args=args or [], fees=fees,
                    consensus_max_rotations=client.chain.default_consensus_max_rotations,
                )
            else:
                returned = client.write_contract(
                    client.w3.to_checksum_address(address), method, account=account,
                    args=args or [], fees=fees,
                )
        except Exception as error:
            journal.update(operation, state="BROADCAST_CALL_RAISED", broadcast_error=str(error))
            raise RuntimeError("broadcast outcome is ambiguous; reserved operation must be reconciled") from error
        tx_hash = _hash_text(returned)
        journal.record_submission(operation, tx_hash)

    try:
        receipt_json, lifecycle, execution = _wait_for_stable_final_receipt(client, tx_hash)
    except Exception as error:
        journal.update(operation, state="POLLING_ERROR", polling_error=str(error))
        raise
    if lifecycle["stored_status"] != "Finalized" or execution != "FINISHED_WITH_RETURN":
        journal.update(operation, state="FINALIZED_EXECUTION_FAILED", lifecycle=lifecycle,
                       execution_result=execution, receipt=receipt_json)
        raise RuntimeError(f"profiling transaction did not succeed: {lifecycle} / {execution}")

    triggered = [_hash_text(value) for value in client.get_triggered_transaction_ids(tx_hash)]
    deployed_address = _contract_address(receipt_json)
    final_address = read_address or deployed_address
    state = None
    if final_address and read_method:
        state = _safe(client.read_contract(
            client.w3.to_checksum_address(str(final_address)), read_method, args=[],
        ))
    journal.update(
        operation, state="FINALIZED_EXECUTED", lifecycle=lifecycle,
        execution_result=execution, receipt=receipt_json,
        triggered_transaction_ids=triggered, address=final_address,
        read_method=read_method, expected_state=state,
    )
    return {
        "operation": operation, "tx": tx_hash, "status": lifecycle["stored_status"],
        "execution": execution, "address": final_address, "state": state,
        "estimate": _safe(estimate), "triggered": triggered,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broadcast", action="store_true")
    args = parser.parse_args()
    if not args.broadcast or os.environ.get("SENTINELX_ALLOW_BROADCAST") != "1":
        parser.error("profiling writes require --broadcast and SENTINELX_ALLOW_BROADCAST=1")
    for path, expected in ((GOVERNOR_SOURCE, "sentinelx_governor.py"), (TARGET_SOURCE, "protected_app_v1.py")):
        if path.name != expected:
            parser.error(f"unexpected source mapping for {path}")
        if not path.is_file():
            parser.error(f"missing exact contract source: {path}")

    try:
        client, account = _client()
        from genlayer_py.types import CalldataAddress

        policy = _safe(client.get_current_fee_policy())
        generic_estimate = _safe(client.estimate_transaction_fees())
        journal = _journal()
        governor = _submit_and_finalize(
            client=client, account=account, journal=journal,
            operation="NON_CANONICAL_PROFILE_ONLY.deploy_governor",
            fee_observation_kind="deploy", contract_name="sentinelx_governor",
            code=GOVERNOR_SOURCE.read_bytes(), read_method="contract_info",
        )
        governor_address = governor["address"]
        if not governor_address:
            raise RuntimeError("finalized governor deployment did not return a contract address")
        target_operation = _operation_for_retry(
            journal, "NON_CANONICAL_PROFILE_ONLY.deploy_target"
        )
        target = _submit_and_finalize(
            client=client, account=account, journal=journal,
            operation=target_operation,
            fee_observation_kind="deploy", contract_name="protected_app_v1",
            code=TARGET_SOURCE.read_bytes(),
            args=[CalldataAddress(governor_address), LABEL, "profile-initial"],
            read_method="get_protected_value",
        )
        target_address = target["address"]
        if not target_address:
            raise RuntimeError("finalized target deployment did not return a contract address")
        write_operation = _operation_for_retry(
            journal, "NON_CANONICAL_PROFILE_ONLY.set_protected_value"
        )
        write = _submit_and_finalize(
            client=client, account=account, journal=journal,
            operation=write_operation,
            fee_observation_kind="method", method="set_protected_value",
            address=target_address, args=["profile-write"],
            read_address=target_address, read_method="get_protected_value",
        )
        print(json.dumps({
            "network": NETWORK, "rpc": RPC, "chain_id": CHAIN_ID,
            "fee_policy": policy, "generic_estimate": generic_estimate,
            "fee_mode": "fee-charging" if policy.get("enabled") else "gasless",
            "label": LABEL, "journal": str(JOURNAL), "governor": governor,
            "target": target, "write": write,
        }, indent=2, sort_keys=True))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
