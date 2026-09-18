"""Stable genlayer-py 0.18 bridge for the disposable Studionet profile.

This module deliberately does not use the RC CLI, RC fee objects, or the
Studio-dev network.  The only credential input is an ephemeral private key
placed in the child process by the local OS-keychain adapter.  It is never
written, logged, or returned by this module.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
RPC = "https://studio.genlayer.com/api"
NETWORK = "studionet"
CHAIN_ID = 61999
EXPECTED_DEPLOYER = "0xCb5a845638Cbc1f95D7f8343278685682c3bA13F"
PROFILE_STATE_NAME = os.environ.get("SENTINELX_STUDIONET_PROFILE_STATE", "studionet-stable-profile-r1")
LOCAL_STATE = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "SentinelX" / PROFILE_STATE_NAME
JOURNAL_PATH = LOCAL_STATE / "transactions.json"


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if hasattr(value, "value"):
        return _safe(value.value)
    return str(value)


def _hash(value: Any) -> str:
    text = value.hex() if isinstance(value, bytes) else str(value)
    if not text.startswith("0x"):
        text = "0x" + text
    if len(text) != 66:
        raise RuntimeError("transaction hash is not a 32-byte hash")
    return text.lower()


def _execution(receipt: dict[str, Any]) -> str:
    direct = str(
        receipt.get("tx_execution_result_name")
        or receipt.get("execution_result")
        or ""
    )
    if direct:
        return direct
    consensus = receipt.get("consensus_data")
    leaders = consensus.get("leader_receipt") if isinstance(consensus, dict) else None
    if isinstance(leaders, list):
        for item in leaders:
            if not isinstance(item, dict):
                continue
            result = str(item.get("execution_result") or "")
            if result == "SUCCESS":
                return "FINISHED_WITH_RETURN"
            if result == "ERROR":
                return "FINISHED_WITH_ERROR"
    return ""


def _status(receipt: dict[str, Any]) -> str:
    value = receipt.get("status_name") or receipt.get("status") or ""
    return getattr(value, "value", str(value))


def _current_fee_policy(client: Any) -> dict[str, Any]:
    """Return the stable SDK-native fee inputs, without RC fee objects."""
    block = client.w3.eth.get_block("latest")
    gas_price = int(client.provider.make_request("eth_gasPrice", [])["result"], 16)
    try:
        priority = int(client.provider.make_request("eth_maxPriorityFeePerGas", [])["result"], 16)
    except Exception:
        priority = 0
    return {
        "source": "genlayer-py-0.18-native",
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "fee_manager_contract": None,
        "eth_gas_price": gas_price,
        "latest_base_fee_per_gas": int(block.get("baseFeePerGas", 0) or 0),
        "max_priority_fee_per_gas": priority,
        "gasless": gas_price == 0 and int(block.get("baseFeePerGas", 0) or 0) == 0,
        "consensus_max_rotations": 3,
        "initial_validators": 5,
        "message_fees": 0,
        "note": "Stable Studionet exposes no RC sim_getFeeConfig; genlayer-py native EVM estimation is authoritative.",
    }


def make_client() -> Any:
    private_key = os.environ.get("SENTINELX_EPHEMERAL_PRIVATE_KEY")
    if not private_key:
        raise RuntimeError("stable managed signer was not supplied to the process")
    from genlayer_py import create_account, create_client
    from genlayer_py.chains import studionet

    if studionet.id != CHAIN_ID or studionet.rpc_urls["default"]["http"][0] != RPC:
        raise RuntimeError("installed stable chain preset is not Studionet 61999")
    key_bytes = bytes.fromhex(private_key.removeprefix("0x"))
    account = create_account(key_bytes)
    if account.address.lower() != EXPECTED_DEPLOYER.lower():
        raise RuntimeError("managed signer public address is not the expected account")
    client: Any = cast(Any, create_client(chain=studionet, account=account))
    chain_response: Any = client.provider.make_request("eth_chainId", [])
    if int(str(chain_response["result"]), 16) != CHAIN_ID:
        raise RuntimeError("RPC chain ID is not Studionet 61999")
    client.get_current_fee_policy = lambda: _current_fee_policy(client)
    client._stable_evm_hash = None
    client._stable_gas_estimate = None
    client._stable_active_operation = None
    client._stable_original_make_request = client.provider.make_request

    def capture_request(method: Any, params: list[Any]) -> Any:
        response = client._stable_original_make_request(method, params)
        if str(method) == "eth_estimateGas" and isinstance(response, dict) and response.get("result"):
            client._stable_gas_estimate = int(str(response["result"]), 16)
        if str(method) == "eth_sendRawTransaction" and isinstance(response, dict) and response.get("result"):
            evm_hash = _hash(response["result"])
            client._stable_evm_hash = evm_hash
            operation = client._stable_active_operation
            if operation:
                # Persist the EVM submission before the stable SDK returns the
                # later GenLayer consensus transaction ID.
                operation["journal"].update(
                    operation["name"],
                    evm_tx_hash=evm_hash,
                    evm_broadcast_persisted=True,
                )
        return response

    client.provider.make_request = capture_request
    return client


def journal() -> Any:
    from scripts.transaction_journal import TransactionJournal

    LOCAL_STATE.mkdir(parents=True, exist_ok=True)
    return TransactionJournal(JOURNAL_PATH)


def account_preflight(client: Any, address: str, journal_obj: Any) -> dict[str, Any]:
    checksum = client.w3.to_checksum_address(address)
    latest = int(client.w3.eth.get_transaction_count(checksum, "latest"))
    pending = int(client.w3.eth.get_transaction_count(checksum, "pending"))
    balance = int(client.w3.eth.get_balance(checksum, "latest"))
    operations = journal_obj.load()["operations"]
    terminal = {
        "FINALIZED_EXECUTED",
        "FINALIZED_EXECUTION_FAILED",
        "BROADCAST_CALL_RAISED",
        "BLOCKED_BEFORE_BROADCAST",
    }
    unresolved = [
        str(name) for name, record in operations.items()
        if isinstance(record, dict) and record.get("state") not in terminal
    ]
    return {
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "address": checksum,
        "balance_wei": balance,
        "latest_nonce": latest,
        "pending_nonce": pending,
        "unresolved_journal_operations": unresolved,
        "fee_policy": _current_fee_policy(client),
    }


def estimate_deploy() -> dict[str, Any]:
    client = make_client()
    return {
        "model": "stable-sdk-native",
        "network": NETWORK,
        "chain_id": CHAIN_ID,
        "message_fees": 0,
        "consensus_max_rotations": 3,
        "fee_policy": _current_fee_policy(client),
        "note": "Actual gas allocation is obtained by genlayer-py eth_estimateGas for each concrete write.",
    }


def source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _persisted_hash(journal_obj: Any, operation: str) -> str | None:
    record = journal_obj.load()["operations"].get(operation)
    if not isinstance(record, dict) or not record.get("tx_hash"):
        return None
    return _hash(record["tx_hash"])


def _contract_address(receipt: dict[str, Any]) -> str | None:
    value = receipt.get("contract_address") or receipt.get("contractAddress") or receipt.get("recipient") or receipt.get("to_address")
    return str(value) if value else None


def _reconcile(client: Any, journal_obj: Any, operation: str, tx_hash: str) -> tuple[dict[str, Any], list[str]]:
    try:
        receipt = _safe(client.wait_for_transaction_receipt(
            tx_hash,
            status="FINALIZED",
            interval=5_000,
            retries=720,
            full_transaction=True,
        ))
    except Exception as error:
        journal_obj.update(operation, state="POLLING_ERROR", polling_error=str(error))
        raise
    status = _status(receipt)
    execution = _execution(receipt)
    if status != "FINALIZED" or execution != "FINISHED_WITH_RETURN":
        journal_obj.update(operation, state="FINALIZED_EXECUTION_FAILED", lifecycle_status=status, execution_result=execution, receipt=receipt)
        raise RuntimeError(f"{operation} did not reach FINALIZED + FINISHED_WITH_RETURN: {status} / {execution}")
    children = [_hash(value) for value in client.get_triggered_transaction_ids(tx_hash)]
    journal_obj.update(
        operation,
        state="FINALIZED_EXECUTED",
        lifecycle_status=status,
        execution_result=execution,
        receipt=receipt,
        triggered_transaction_ids=children,
    )
    return receipt, children


def submit(
    *, client: Any, journal_obj: Any, operation: str, kind: str,
    method: str | None = None, address: str | None = None,
    args: list[Any] | None = None, source: Path | None = None,
    fee_metadata: dict[str, object] | None = None,
) -> dict[str, Any]:
    existing = _persisted_hash(journal_obj, operation)
    if existing:
        existing_record = journal_obj.load()["operations"].get(operation, {})
        # A resumed profile must not re-poll every historical transaction.
        # The journal is written only after the authoritative FINALIZED /
        # FINISHED_WITH_RETURN check, so rehydrate that immutable observation
        # locally.  Non-terminal or incomplete records still take the normal
        # reconciliation path below.
        if (
            existing_record.get("state") == "FINALIZED_EXECUTED"
            and existing_record.get("lifecycle_status") == "FINALIZED"
            and existing_record.get("execution_result") == "FINISHED_WITH_RETURN"
        ):
            children = existing_record.get("triggered_transaction_ids", [])
            return {
                "tx_hash": existing,
                "receipt": existing_record.get("receipt", {}),
                "children": list(children) if isinstance(children, list) else [],
                "reused": True,
            }
        receipt, children = _reconcile(client, journal_obj, operation, existing)
        return {"tx_hash": existing, "receipt": receipt, "children": children, "reused": True}
    if operation in journal_obj.load()["operations"]:
        raise RuntimeError(f"operation {operation!r} is reserved without a stable transaction hash; reconcile manually")
    preflight = account_preflight(client, EXPECTED_DEPLOYER, journal_obj)
    if int(preflight["latest_nonce"]) != int(preflight["pending_nonce"]):
        raise RuntimeError("latest and pending nonce differ; unknown pending activity blocks writes")
    if preflight["unresolved_journal_operations"]:
        raise RuntimeError("unresolved local stable transaction journal blocks writes")
    metadata: dict[str, Any] = {
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "fee_observation_kind": kind,
        "method": method,
        "address": address,
        "fee_model": "stable-sdk-native",
        "message_fees": 0,
        "fee_policy": _current_fee_policy(client),
        **(fee_metadata or {}),
    }
    journal_obj.reserve_broadcast(operation, **metadata)
    client._stable_active_operation = {"name": operation, "journal": journal_obj}
    client._stable_evm_hash = None
    client._stable_gas_estimate = None
    values = args or []
    try:
        account = client.local_account
        if source is not None:
            tx_hash = client.deploy_contract(
                source.read_bytes(), account=account, args=values,
                consensus_max_rotations=client.chain.default_consensus_max_rotations,
            )
        else:
            if not address or not method:
                raise RuntimeError("stable write requires address and method")
            tx_hash = client.write_contract(
                client.w3.to_checksum_address(address), method, account=account,
                args=values,
                consensus_max_rotations=client.chain.default_consensus_max_rotations,
            )
    except Exception as error:
        journal_obj.update(operation, state="BROADCAST_CALL_RAISED", broadcast_error=str(error))
        raise
    finally:
        client._stable_active_operation = None
    tx_hash = _hash(tx_hash)
    journal_obj.record_submission(operation, tx_hash)
    evm_hash = client._stable_evm_hash
    if evm_hash:
        try:
            evm_receipt = _safe(client.w3.eth.get_transaction_receipt(evm_hash))
        except Exception as error:
            evm_receipt = {"read_error": str(error)}
        journal_obj.update(
            operation,
            evm_tx_hash=evm_hash,
            evm_receipt=evm_receipt,
            gas_estimate=client._stable_gas_estimate,
        )
    receipt, children = _reconcile(client, journal_obj, operation, tx_hash)
    return {"tx_hash": tx_hash, "receipt": receipt, "children": children, "reused": False}


def read(client: Any, address: str, method: str, args: list[Any] | None = None) -> Any:
    from genlayer_py.types.transactions import TransactionHashVariant

    for attempt in range(4):
        try:
            return _safe(client.read_contract(
                client.w3.to_checksum_address(address), method,
                args=args or [], transaction_hash_variant=TransactionHashVariant.LATEST_FINAL,
            ))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2)


def read_json(client: Any, address: str, method: str, args: list[Any] | None = None) -> dict[str, Any]:
    value = read(client, address, method, args)
    if not isinstance(value, str):
        raise RuntimeError(f"{method} did not return JSON text")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{method} did not return a JSON object")
    return parsed


def track_children(*, client: Any, journal_obj: Any, parent_operation: str, children: list[str], depth: int = 5) -> list[str]:
    if depth <= 0:
        return []
    all_children: list[str] = []
    for index, child_hash in enumerate(children):
        child_operation = f"{parent_operation}.child.{index}"
        existing = _persisted_hash(journal_obj, child_operation)
        existing_record = journal_obj.load()["operations"].get(child_operation, {})
        if (
            existing
            and existing_record.get("state") == "FINALIZED_EXECUTION_FAILED"
            and existing_record.get("lifecycle_status") == "FINALIZED"
        ):
            # Negative child executions are terminal observations too.  Keep
            # their hash for coverage and do not turn a completed negative
            # proof into an artificial unresolved transaction on resume.
            all_children.append(_hash(child_hash))
            continue
        if existing is None:
            journal_obj.reserve_broadcast(child_operation, parent_operation=parent_operation, fee_observation_kind="child")
            journal_obj.record_submission(child_operation, _hash(child_hash), parent_operation=parent_operation)
        _, grandchildren = _reconcile(client, journal_obj, child_operation, existing or _hash(child_hash))
        all_children.append(_hash(child_hash))
        all_children.extend(track_children(client=client, journal_obj=journal_obj, parent_operation=child_operation, children=grandchildren, depth=depth - 1))
    return all_children


def deployed_source(client: Any, address: str) -> bytes:
    response = client.provider.make_request("gen_getContractCode", [client.w3.to_checksum_address(address)])
    encoded = response.get("result") if isinstance(response, dict) else None
    if not isinstance(encoded, str):
        raise RuntimeError("stable source readback did not return base64 code")
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as error:
        raise RuntimeError("stable source readback was not valid base64") from error


def verify_source(client: Any, address: str, source: Path) -> dict[str, Any]:
    deployed = deployed_source(client, address)
    expected = source.read_bytes()
    if deployed != expected:
        raise RuntimeError(f"deployed source parity failed for {source.name}")
    return {"parity": True, "sha256": hashlib.sha256(deployed).hexdigest(), "bytes": len(deployed)}
