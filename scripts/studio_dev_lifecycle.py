"""Fee-aware, no-blind-rebroadcast Studio-dev lifecycle runner.

The write subcommands are deliberately locked behind two explicit controls:
``--broadcast`` and ``SENTINELX_ALLOW_BROADCAST=1``.  Every write also needs a
real measured ``fee-profile.json``.  This makes it possible to prepare the
canonical flow before an independent security publisher and fee observations
exist, without accidentally creating chain state.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RPC = "https://studio-dev.genlayer.com/api"
NETWORK = "studio-dev"
CHAIN_ID = 61997
PROFILE = ROOT / "fee-profile.json"
JOURNAL = ROOT / "artifacts" / "studio-dev-transactions.json"
DEFAULT_APPEAL_ROUNDS = 1


def _json_value(value: Any) -> Any:
    """Make SDK enums/bytes safe to persist as journal metadata."""
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if hasattr(value, "value"):
        return _json_value(value.value)
    return value


def _enum_text(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def _hash_text(value: Any) -> str:
    text = value.hex() if isinstance(value, bytes) else str(value)
    if not text.startswith("0x"):
        text = "0x" + text
    if len(text) != 66 or any(char not in "0123456789abcdefABCDEF" for char in text[2:]):
        raise ValueError("SDK returned an invalid 32-byte transaction hash")
    return text.lower()


def load_account() -> Any:
    private_key = os.environ.get("SENTINELX_PRIVATE_KEY")
    if not private_key:
        raise RuntimeError("SENTINELX_PRIVATE_KEY is required only for an authorized write")
    from eth_account import Account

    try:
        return Account.from_key(private_key)
    except (TypeError, ValueError) as error:
        raise RuntimeError("SENTINELX_PRIVATE_KEY is invalid") from error


def make_client(*, with_account: bool) -> Any:
    from genlayer_py import create_client
    from genlayer_py.chains import studio_devnet

    if studio_devnet.id != CHAIN_ID or studio_devnet.rpc_urls["default"]["http"][0] != RPC:
        raise RuntimeError("installed GenLayerPY chain configuration is not Studio-dev 61997")
    account = load_account() if with_account else None
    return create_client(chain=studio_devnet, account=account)


def account_preflight(client: Any, address: str) -> dict[str, object]:
    checksum = client.w3.to_checksum_address(address)
    latest = int(client.get_current_nonce(checksum, "latest"))
    pending = int(client.get_transaction_count(checksum, "pending"))
    balance = int(client.get_balance(checksum, "latest"))
    journal = __import__("scripts.transaction_journal", fromlist=["TransactionJournal"]).TransactionJournal(JOURNAL)
    operations = journal.load()["operations"]
    known_hashes = [record.get("tx_hash") for record in operations.values() if isinstance(record, dict)]
    return {
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "address": checksum,
        "balance_wei": balance,
        "latest_nonce": latest,
        "pending_nonce": pending,
        "known_journal_hashes": [value for value in known_hashes if value],
        "pending_pool_rpc": "not exposed by current Studio-dev endpoint",
        "unknown_pending_transactions": "UNKNOWN outside the journal",
    }


def _journal(path: Path) -> Any:
    from scripts.transaction_journal import TransactionJournal

    return TransactionJournal(path)


def _profile(path: Path) -> dict[str, object]:
    from scripts.fee_aware_transaction import load_fee_profile

    return load_fee_profile(
        path,
        required_methods=(
            "register_with_sentinelx",
            "register_target",
            "create_proposal",
            "review_proposal",
            "repair_evidence",
            "retry_review",
            "cancel_proposal",
            "expire_proposal",
            "reconcile_install",
            "mark_execution_timeout",
            "confirm_install",
            "install_reviewed_upgrade",
        ),
        network="studio_devnet",
        chain_id=CHAIN_ID,
    )


def _fees_for_write(
    client: Any,
    profile: dict[str, object],
    *,
    address: str,
    method: str,
    account: Any,
    args: list[Any],
    appeal_rounds: int,
) -> dict[str, Any]:
    from scripts.fee_aware_transaction import fee_options_from_result, profile_entry_to_estimate_options

    methods = profile.get("methods")
    entry = methods.get(method) if isinstance(methods, dict) else None
    if not isinstance(entry, dict):
        raise ValueError(f"fee profile lacks a measured {method} operation")
    options = profile_entry_to_estimate_options(entry, appeal_rounds=appeal_rounds)
    estimate = client.estimate_transaction_fees_for_write(
        client.w3.to_checksum_address(address),
        method,
        account=account,
        args=args,
        options=options,
        transaction_hash_variant=_latest_nonfinal_variant(),
    )
    return fee_options_from_result(estimate).as_sdk_fees()


def _fees_for_deploy(client: Any, profile: dict[str, object], *, appeal_rounds: int) -> dict[str, Any]:
    from scripts.fee_aware_transaction import fee_options_from_result, profile_entry_to_estimate_options

    entry = profile.get("deploy")
    if not isinstance(entry, dict):
        raise ValueError("fee profile lacks a measured deploy operation")
    options = profile_entry_to_estimate_options(entry, appeal_rounds=appeal_rounds)
    return fee_options_from_result(client.estimate_transaction_fees(options)).as_sdk_fees()


def _latest_nonfinal_variant() -> Any:
    from genlayer_py.types.transactions import TransactionHashVariant

    return TransactionHashVariant.LATEST_NONFINAL


def _latest_final_variant() -> Any:
    from genlayer_py.types.transactions import TransactionHashVariant

    return TransactionHashVariant.LATEST_FINAL


def _submit_once(
    *,
    client: Any,
    account: Any,
    profile: dict[str, object],
    journal: Any,
    operation: str,
    method: str | None,
    address: str | None,
    args: list[Any],
    code: bytes | None = None,
    appeal_rounds: int = DEFAULT_APPEAL_ROUNDS,
    metadata: dict[str, object] | None = None,
) -> str:
    """Estimate, reserve, send exactly once, and persist the returned hash."""
    if method is None and code is None:
        raise ValueError("a deploy needs code and a write needs a method")
    fees = (
        _fees_for_deploy(client, profile, appeal_rounds=appeal_rounds)
        if code is not None
        else _fees_for_write(
            client, profile, address=str(address), method=str(method), account=account,
            args=args, appeal_rounds=appeal_rounds,
        )
    )
    journal.reserve_broadcast(operation, method=method, address=address, **(metadata or {}))
    try:
        if code is not None:
            returned = client.deploy_contract(
                code, account=account, args=args, fees=fees,
                consensus_max_rotations=client.chain.default_consensus_max_rotations,
            )
        else:
            returned = client.write_contract(
                client.w3.to_checksum_address(str(address)), str(method),
                account=account, args=args, fees=fees,
            )
    except Exception as error:
        # The reservation is the durable instruction to reconcile manually.
        journal.update(operation, state="BROADCAST_CALL_RAISED", broadcast_error=str(error))
        raise RuntimeError(
            "broadcast outcome is ambiguous; operation is reserved and must be reconciled, not retried"
        ) from error
    tx_hash = _hash_text(returned)
    journal.record_submission(operation, tx_hash)
    return tx_hash


def inspect_lifecycle(client: Any, tx_hash: str) -> dict[str, object]:
    lifecycle = client.get_transaction_lifecycle(tx_hash)
    action = _enum_text(lifecycle.get("resolution_action_name"))
    if action == "ReadyToFinalize":
        raise RuntimeError("legacy ReadyToFinalize is not a supported v0.6 status/action")
    if action == "Finalize":
        decision_id = lifecycle.get("decision_id")
        if not lifecycle.get("decision_active") or decision_id is None or not str(decision_id).isdigit():
            raise RuntimeError("Finalize action lacks an active decision ID")
    return {
        "stored_status": _enum_text(lifecycle.get("stored_status_name")),
        "projected_status": _enum_text(lifecycle.get("projected_status_name")),
        "resolution_action": action,
        "decision_id": lifecycle.get("decision_id"),
        "decision_active": bool(lifecycle.get("decision_active")),
        "evaluated_at": lifecycle.get("evaluated_at"),
    }


def reconcile_genlayer(
    *, client: Any, journal: Any, operation: str,
) -> tuple[dict[str, Any], dict[str, object]]:
    """Track one existing hash; timeout never causes a rebroadcast."""
    record = journal.load()["operations"].get(operation)
    if not isinstance(record, dict) or not record.get("tx_hash"):
        raise RuntimeError("operation has no persisted transaction hash")
    tx_hash = str(record["tx_hash"])
    try:
        receipt = client.wait_for_transaction_receipt(
            tx_hash, wait_until="finalized", full_transaction=True
        )
        lifecycle = inspect_lifecycle(client, tx_hash)
    except Exception as error:
        journal.update(operation, state="POLLING_ERROR", polling_error=str(error))
        raise
    from genlayer_py.transactions import is_successful

    execution = receipt.get("tx_execution_result_name")
    if lifecycle["stored_status"] != "Finalized":
        journal.update(operation, state="NOT_FINALIZED", lifecycle=lifecycle)
        raise RuntimeError("receipt wait returned without a Finalized stored status")
    if execution != "FINISHED_WITH_RETURN" or not is_successful(receipt):
        journal.update(
            operation, state="FINALIZED_EXECUTION_FAILED", lifecycle=lifecycle,
            execution_result=execution,
        )
        raise RuntimeError("finality without FINISHED_WITH_RETURN is not successful execution")
    children = [_hash_text(value) for value in client.get_triggered_transaction_ids(tx_hash)]
    saved = journal.update(
        operation, state="FINALIZED_EXECUTED", lifecycle=lifecycle,
        execution_result=execution, triggered_transaction_ids=children,
    )
    return receipt, saved


def reconcile_review_decision(
    *, client: Any, journal: Any, operation: str,
) -> tuple[dict[str, Any], dict[str, object]]:
    """Observe Accepted without treating it as Finalized."""
    record = journal.load()["operations"].get(operation)
    if not isinstance(record, dict) or not record.get("tx_hash"):
        raise RuntimeError("review operation has no persisted transaction hash")
    tx_hash = str(record["tx_hash"])
    try:
        receipt = client.wait_for_transaction_receipt(
            tx_hash, wait_until="decided", full_transaction=True
        )
        lifecycle = inspect_lifecycle(client, tx_hash)
    except Exception as error:
        journal.update(operation, state="POLLING_ERROR", polling_error=str(error))
        raise
    status = str(lifecycle["stored_status"])
    if status not in ("Accepted", "Finalized"):
        journal.update(operation, state="DECISION_NOT_ACCEPTED", lifecycle=lifecycle,
                       execution_result=receipt.get("tx_execution_result_name"))
        raise RuntimeError(f"review did not reach Accepted/Finalized: {status}")
    saved = journal.update(
        operation,
        state="DECIDED_ACCEPTED" if status == "Accepted" else "FINALIZED_OBSERVED",
        lifecycle=lifecycle,
        execution_result=receipt.get("tx_execution_result_name"),
    )
    return receipt, saved


def read_expected_state(
    client: Any, *, address: str, function: str, args: list[Any]
) -> Any:
    if not address or not function:
        raise ValueError("expected final-state address and view are required")
    return client.read_contract(
        client.w3.to_checksum_address(address), function, args=args,
        transaction_hash_variant=_latest_final_variant(),
    )


def track_child_tree(
    *, client: Any, journal: Any, parent_operation: str, parent_hash: str, depth: int = 2
) -> list[str]:
    """Persist and track already-created child IDs, never create replacements."""
    if depth <= 0:
        return []
    children = [_hash_text(value) for value in client.get_triggered_transaction_ids(parent_hash)]
    all_children: list[str] = []
    for index, child_hash in enumerate(children):
        child_operation = f"{parent_operation}.child.{index}"
        journal.record_child(parent_operation, child_operation, child_hash)
        reconcile_genlayer(client=client, journal=journal, operation=child_operation)
        all_children.append(child_hash)
        all_children.extend(track_child_tree(
            client=client, journal=journal, parent_operation=child_operation,
            parent_hash=child_hash, depth=depth - 1,
        ))
    return all_children


def finalize_decision_once(*, client: Any, account: Any, journal: Any, source_operation: str) -> str:
    """Use the active decision ID in the v0.6 Finalize action exactly once."""
    record = journal.load()["operations"].get(source_operation)
    if not isinstance(record, dict) or not record.get("tx_hash"):
        raise RuntimeError("source transaction is not journaled")
    lifecycle = inspect_lifecycle(client, str(record["tx_hash"]))
    if lifecycle["resolution_action"] != "Finalize":
        raise RuntimeError("current lifecycle does not expose the Finalize resolution action")
    decision_id = lifecycle["decision_id"]
    if not lifecycle["decision_active"] or decision_id is None:
        raise RuntimeError("Finalize requires an active decision ID")
    web3 = client.w3
    contract_info = client.chain.consensus_main_contract
    if not isinstance(contract_info, dict):
        raise RuntimeError("Studio-dev consensus main contract ABI is unavailable")
    contract = web3.eth.contract(
        address=web3.to_checksum_address(str(contract_info["address"])),
        abi=contract_info["abi"],
    )
    sender = web3.to_checksum_address(account.address)
    nonce = int(web3.eth.get_transaction_count(sender, "pending"))
    gas_price = int(web3.eth.gas_price)
    call = contract.functions.finalizeTransaction(
        str(record["tx_hash"]), int(str(decision_id))
    )
    unsigned = call.build_transaction({"from": sender, "nonce": nonce, "gasPrice": gas_price})
    unsigned["gas"] = int(web3.eth.estimate_gas(unsigned))
    operation = f"{source_operation}.finalize.decision-{decision_id}"
    journal.reserve_broadcast(operation, source_operation=source_operation, decision_id=str(decision_id))
    signed = account.sign_transaction(unsigned)
    try:
        returned = web3.eth.send_raw_transaction(signed.raw_transaction)
    except Exception as error:
        journal.update(operation, state="BROADCAST_CALL_RAISED", broadcast_error=str(error))
        raise RuntimeError("finalization broadcast is ambiguous; reconcile the reserved EVM hash") from error
    tx_hash = _hash_text(returned)
    journal.record_submission(operation, tx_hash, transaction_kind="evm", parent_operation=source_operation)
    try:
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    except Exception as error:
        journal.update(operation, state="POLLING_ERROR", polling_error=str(error))
        raise
    if int(receipt.get("status", 0)) != 1:
        journal.update(operation, state="FINALIZED_EXECUTION_FAILED", evm_receipt=_json_value(receipt))
        raise RuntimeError("EVM finalization transaction failed")
    journal.update(operation, state="FINALIZED_EXECUTED", evm_receipt=_json_value(receipt))
    return tx_hash


def _read_args(value: str) -> list[Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("--args-json must contain a JSON array")
    return parsed


def _ensure_broadcast_allowed(args: argparse.Namespace) -> None:
    if not args.broadcast or os.environ.get("SENTINELX_ALLOW_BROADCAST") != "1":
        raise RuntimeError("writes require --broadcast and SENTINELX_ALLOW_BROADCAST=1")


def _assert_account_precondition(preflight: dict[str, object]) -> None:
    latest = int(str(preflight["latest_nonce"]))
    pending = int(str(preflight["pending_nonce"]))
    if latest != pending:
        raise RuntimeError(
            "pending nonce differs from latest nonce; unknown pending activity must be reconciled before any write"
        )


def run_review(args: argparse.Namespace) -> dict[str, object]:
    """Run the review write through decision-bound v0.6 finalization."""
    _ensure_broadcast_allowed(args)
    account = load_account()
    client = make_client(with_account=True)
    profile = _profile(args.fee_profile)
    journal = _journal(args.journal)
    preflight = account_preflight(client, account.address)
    _assert_account_precondition(preflight)
    args_list = _read_args(args.args_json)
    tx_hash = _submit_once(
        client=client, account=account, profile=profile, journal=journal,
        operation=args.operation, method="review_proposal", address=args.address,
        args=args_list,
    )
    decided_receipt, decision_record = reconcile_review_decision(
        client=client, journal=journal, operation=args.operation
    )
    lifecycle = decision_record["lifecycle"]
    if isinstance(lifecycle, dict) and lifecycle.get("stored_status") == "Accepted":
        finalize_decision_once(
            client=client, account=account, journal=journal, source_operation=args.operation
        )
    final_receipt, final_record = reconcile_genlayer(
        client=client, journal=journal, operation=args.operation
    )
    child_hashes = track_child_tree(
        client=client, journal=journal, parent_operation=args.operation,
        parent_hash=tx_hash, depth=args.child_depth,
    )
    if not args.expected_read_address:
        raise RuntimeError("review requires an expected governor read address")
    state = read_expected_state(
        client, address=args.expected_read_address, function=args.expected_read_function,
        args=_read_args(args.expected_read_args_json),
    )
    return {
        "operation": args.operation,
        "tx_hash": tx_hash,
        "decision_receipt": _json_value(decided_receipt.get("lifecycle")),
        "final_receipt": _json_value(final_receipt.get("lifecycle")),
        "journal": final_record,
        "child_hashes": child_hashes,
        "expected_state": _json_value(state),
    }


def run_write(args: argparse.Namespace) -> dict[str, object]:
    _ensure_broadcast_allowed(args)
    account = load_account()
    client = make_client(with_account=True)
    profile = _profile(args.fee_profile)
    journal = _journal(args.journal)
    # This read is the account precondition for every write operation.
    preflight = account_preflight(client, account.address)
    _assert_account_precondition(preflight)
    code = Path(args.code).read_bytes() if args.code else None
    method = None if code is not None else args.method
    address = None if code is not None else args.address
    tx_hash = _submit_once(
        client=client, account=account, profile=profile, journal=journal,
        operation=args.operation, method=method, address=address,
        args=_read_args(args.args_json), code=code,
    )
    receipt, record = reconcile_genlayer(client=client, journal=journal, operation=args.operation)
    child_hashes = track_child_tree(
        client=client, journal=journal, parent_operation=args.operation,
        parent_hash=tx_hash, depth=args.child_depth,
    )
    expected_address = args.expected_read_address
    if code is not None:
        expected_address = receipt.get("contract_address") or receipt.get("recipient")
    if not expected_address:
        raise RuntimeError("successful write has no expected final-state address")
    state = read_expected_state(
        client, address=str(expected_address), function=args.expected_read_function,
        args=_read_args(args.expected_read_args_json),
    )
    return {
        "operation": args.operation,
        "tx_hash": tx_hash,
        "receipt_lifecycle": _json_value(receipt.get("lifecycle")),
        "journal": record,
        "child_hashes": child_hashes,
        "expected_state": _json_value(state),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    account_cmd = sub.add_parser("account-preflight")
    account_cmd.add_argument("--address", required=True)
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--operation", required=True)
    reconcile.add_argument("--journal", type=Path, default=JOURNAL)
    reconcile.add_argument("--expected-read-address", required=True)
    reconcile.add_argument("--expected-read-function", required=True)
    reconcile.add_argument("--expected-read-args-json", default="[]")
    finalize = sub.add_parser("finalize")
    finalize.add_argument("--operation", required=True)
    finalize.add_argument("--journal", type=Path, default=JOURNAL)
    write_commands = ("deploy-governor", "deploy-target", "registration", "proposal", "review")
    method_by_command = {
        "registration": "register_with_sentinelx",
        "proposal": "create_proposal",
        "review": "review_proposal",
    }
    code_name_by_command = {
        "deploy-governor": "sentinelx_governor.py",
        "deploy-target": "protected_app_v1.py",
    }
    for name in write_commands:
        item = sub.add_parser(name)
        item.add_argument("--broadcast", action="store_true")
        item.add_argument("--fee-profile", type=Path, default=PROFILE)
        item.add_argument("--journal", type=Path, default=JOURNAL)
        item.add_argument("--operation", required=True)
        item.add_argument("--code", type=Path if name.startswith("deploy") else str,
                          required=name.startswith("deploy"))
        item.add_argument("--address", required=not name.startswith("deploy"))
        if name in method_by_command:
            item.add_argument("--method", choices=[method_by_command[name]], default=method_by_command[name])
        item.add_argument("--args-json", required=True)
        item.add_argument("--expected-read-address")
        item.add_argument("--expected-read-function", default="contract_info")
        item.add_argument("--expected-read-args-json", default="[]")
        item.add_argument("--child-depth", type=int, default=2)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            print(json.dumps({
                "network": NETWORK, "rpc": RPC, "chain_id": CHAIN_ID,
                "write_order": [
                    "precondition_read", "live_fee_quote", "broadcast_once",
                    "persist_hash", "track_same_hash", "finalized_lifecycle",
                    "successful_execution", "expected_state_read",
                ],
                "broadcast_gate": "--broadcast + SENTINELX_ALLOW_BROADCAST=1",
                "fee_profile": str(PROFILE),
            }, indent=2, sort_keys=True))
            return 0
        if args.command == "account-preflight":
            print(json.dumps(account_preflight(make_client(with_account=False), args.address), indent=2, sort_keys=True))
            return 0
        if args.command == "reconcile":
            client = make_client(with_account=False)
            journal = _journal(args.journal)
            receipt, _ = reconcile_genlayer(client=client, journal=journal, operation=args.operation)
            state = read_expected_state(client, address=args.expected_read_address,
                                        function=args.expected_read_function,
                                        args=_read_args(args.expected_read_args_json))
            print(json.dumps({"receipt": _json_value(receipt), "expected_state": _json_value(state)}, indent=2, sort_keys=True))
            return 0
        if args.command == "finalize":
            account = load_account()
            tx_hash = finalize_decision_once(client=make_client(with_account=True), account=account,
                                             journal=_journal(args.journal), source_operation=args.operation)
            print(tx_hash)
            return 0
        if args.command == "review":
            print(json.dumps(run_review(args), indent=2, sort_keys=True))
        else:
            if args.command.startswith("deploy"):
                expected_name = code_name_by_command[args.command]
                if args.code.name != expected_name:
                    raise ValueError(f"{args.command} requires the exact local source file {expected_name}")
            print(json.dumps(run_write(args), indent=2, sort_keys=True))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
