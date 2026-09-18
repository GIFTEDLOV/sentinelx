"""Run isolated, disposable Studionet cross-contract view probes.

This script is intentionally separate from the SentinelX qualification
orchestrators.  It deploys only contracts whose source files are marked
``NON_PRODUCTION_DIAGNOSTIC_ONLY`` and never writes to the historical V2.2
profile except through fresh diagnostic callers that read its target state.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SENTINELX_STUDIONET_PROFILE_STATE", "studionet-finalized-view-probes-r1")

from scripts import studionet_stable_bridge as bridge  # noqa: E402


NETWORK = "studionet"
RPC = "https://studio.genlayer.com/api"
CHAIN_ID = 61999
CURRENT_PROFILE_GOVERNOR = "0x2DCDbcC22B0b9B27dE2736A2469AE95755C7fc73"
UPGRADED_PROFILE_TARGET = "0x4c725401BCC000DAC7e52f5D6c5D3Dd5105fa6F2"
TARGET_SOURCE = ROOT / "contracts" / "finalized_view_probe_target.py"
TYPED_CALLER_SOURCE = ROOT / "contracts" / "finalized_view_probe_caller.py"
SENTINELX_CALLER_SOURCE = ROOT / "contracts" / "sentinelx_view_probe_caller.py"
BASELINE_SOURCE = ROOT / "contracts" / "protected_app_v1.py"
OUTPUT = ROOT / "artifacts" / "studionet" / "finalized-view-probe-results.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _record(journal_obj: Any, operation: str) -> dict[str, Any]:
    value = journal_obj.load()["operations"].get(operation)
    return value if isinstance(value, dict) else {}


def _receipt_summary(record: dict[str, Any]) -> dict[str, Any]:
    receipt = record.get("receipt")
    receipt_obj = receipt if isinstance(receipt, dict) else {}
    consensus = receipt_obj.get("consensus_data")
    consensus_obj = consensus if isinstance(consensus, dict) else {}
    return {
        "stored_state": record.get("state"),
        "status": record.get("lifecycle_status") or receipt_obj.get("status_name") or receipt_obj.get("status"),
        "execution": record.get("execution_result") or bridge._execution(receipt_obj),
        "tx_hash": record.get("tx_hash"),
        "evm_tx_hash": record.get("evm_tx_hash"),
        "error_code": receipt_obj.get("error_code") or record.get("error_code"),
        "error_class": receipt_obj.get("error_class") or record.get("error_class"),
        "error_message": receipt_obj.get("error_message") or receipt_obj.get("error") or record.get("broadcast_error") or record.get("polling_error"),
        "genvm_error": receipt_obj.get("genvm_error") or receipt_obj.get("genvm_error_code"),
        "stdout": receipt_obj.get("stdout"),
        "stderr": receipt_obj.get("stderr") or record.get("stderr"),
        "consensus_result": consensus_obj.get("result") or consensus_obj.get("status") or receipt_obj.get("result_name") or record.get("consensus_result"),
        "result_name": receipt_obj.get("result_name") or record.get("consensus_result"),
    }


def _rpc_transaction(client: Any, tx_hash: str) -> dict[str, Any] | None:
    response = client.provider.make_request("eth_getTransactionByHash", [tx_hash])
    value = response.get("result") if isinstance(response, dict) else None
    return value if isinstance(value, dict) else None


def _submit_diagnostic(
    *, client: Any, journal_obj: Any, operation: str, kind: str,
    method: str | None = None, address: str | None = None,
    args: list[Any] | None = None, source: Path | None = None,
    fee_metadata: dict[str, object] | None = None,
) -> dict[str, Any]:
    """Submit once, then observe raw lifecycle/result without hidden retries.

    The stable SDK waiter does not terminate for the observed Studionet shape
    ``PROPOSING + result_name=NO_MAJORITY``.  The raw RPC result is authoritative
    for this diagnostic, so the helper records that result as a terminal
    consensus failure while preserving the exact submitted hash.
    """
    if operation in journal_obj.load()["operations"]:
        raise RuntimeError(f"diagnostic operation {operation!r} is already journaled")
    preflight = bridge.account_preflight(client, bridge.EXPECTED_DEPLOYER, journal_obj)
    terminal_states = {
        "FINALIZED_EXECUTED", "FINALIZED_EXECUTION_FAILED",
        "BROADCAST_CALL_RAISED", "BLOCKED_BEFORE_BROADCAST",
        "TERMINAL_CONSENSUS_FAILURE", "OBSERVED_NO_MAJORITY",
    }
    preflight["unresolved_journal_operations"] = [
        name for name, record in journal_obj.load()["operations"].items()
        if isinstance(record, dict) and record.get("state") not in terminal_states
    ]
    if int(preflight["latest_nonce"]) != int(preflight["pending_nonce"]):
        raise RuntimeError("latest and pending nonce differ before diagnostic write")
    if preflight["unresolved_journal_operations"]:
        raise RuntimeError("unresolved diagnostic journal operation blocks the next write")
    journal_obj.reserve_broadcast(
        operation,
        network=NETWORK,
        rpc=RPC,
        chain_id=CHAIN_ID,
        fee_observation_kind=kind,
        method=method,
        address=address,
        fee_model="stable-sdk-native",
        message_fees=0,
        **(fee_metadata or {}),
    )
    client._stable_active_operation = {"name": operation, "journal": journal_obj}
    client._stable_evm_hash = None
    client._stable_gas_estimate = None
    try:
        if source is not None:
            tx_value = client.deploy_contract(
                source.read_bytes(), account=client.local_account, args=args or [],
                consensus_max_rotations=client.chain.default_consensus_max_rotations,
            )
        else:
            if not address or not method:
                raise RuntimeError("diagnostic write requires address and method")
            tx_value = client.write_contract(
                client.w3.to_checksum_address(address), method,
                account=client.local_account, args=args or [],
                consensus_max_rotations=client.chain.default_consensus_max_rotations,
            )
    except Exception as error:
        journal_obj.update(operation, state="BROADCAST_CALL_RAISED", broadcast_error=str(error))
        raise
    finally:
        client._stable_active_operation = None
    tx_hash = bridge._hash(tx_value)
    journal_obj.record_submission(operation, tx_hash)
    evm_hash = client._stable_evm_hash
    if evm_hash:
        journal_obj.update(operation, evm_tx_hash=evm_hash, gas_estimate=client._stable_gas_estimate)

    terminal_result_names = {
        "NO_MAJORITY", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT", "UNDETERMINED",
    }
    observed: dict[str, Any] | None = None
    last_signature = ""
    last_progress = time.monotonic()
    for _ in range(240):
        observed = _rpc_transaction(client, tx_hash)
        if observed is not None:
            status = str(observed.get("status_name") or observed.get("status") or "")
            result_name = str(observed.get("result_name") or "")
            execution = bridge._execution(observed)
            history = observed.get("consensus_history")
            last_round = observed.get("last_round")
            signature = json.dumps({
                "status": status,
                "result_name": result_name,
                "history": history.get("current_status_changes") if isinstance(history, dict) else None,
                "last_round": last_round,
            }, sort_keys=True, default=str)
            if signature != last_signature:
                last_signature = signature
                last_progress = time.monotonic()
            if status == "FINALIZED":
                if execution == "FINISHED_WITH_RETURN":
                    journal_obj.update(
                        operation, state="FINALIZED_EXECUTED", lifecycle_status=status,
                        execution_result=execution, receipt=bridge._safe(observed),
                        triggered_transaction_ids=[
                            bridge._hash(value) for value in client.get_triggered_transaction_ids(tx_hash)
                        ],
                    )
                    return {"tx_hash": tx_hash, "receipt": bridge._safe(observed), "children": []}
                journal_obj.update(
                    operation, state="FINALIZED_EXECUTION_FAILED", lifecycle_status=status,
                    execution_result=execution, consensus_result=result_name,
                    receipt=bridge._safe(observed),
                )
                return {"tx_hash": tx_hash, "receipt": bridge._safe(observed), "children": []}
            # Some Studionet responses project NO_MAJORITY while validators
            # are still being selected/executed.  Classify it only after the
            # raw lifecycle has been unchanged for a sustained window and
            # the round still has no validator activity.
            votes = last_round.get("votes_committed", 0) if isinstance(last_round, dict) else 0
            if (
                result_name in terminal_result_names
                and int(votes or 0) == 0
                and time.monotonic() - last_progress >= 180
            ):
                journal_obj.update(
                    operation, state="OBSERVED_NO_MAJORITY", lifecycle_status=status,
                    execution_result=execution or "NOT_EXECUTED", consensus_result=result_name,
                    receipt=bridge._safe(observed),
                )
                return {"tx_hash": tx_hash, "receipt": bridge._safe(observed), "children": []}
        time.sleep(5)
    journal_obj.update(operation, state="POLLING_ERROR", polling_error="diagnostic observation window expired")
    raise RuntimeError(f"diagnostic transaction {tx_hash} did not reach an observed terminal result")


def _attempt(
    *, client: Any, journal_obj: Any, operation: str, method: str,
    address: str, args: list[Any], readback: tuple[str, str, list[Any]] | None = None,
) -> dict[str, Any]:
    try:
        result = _submit_diagnostic(
            client=client,
            journal_obj=journal_obj,
            operation=operation,
            kind="diagnostic",
            method=method,
            address=address,
            args=args,
            fee_metadata={"diagnostic_only": True, "emitted_child_messages": 0},
        )
        item = _receipt_summary(_record(journal_obj, operation))
        successful = (
            item.get("stored_state") == "FINALIZED_EXECUTED"
            and item.get("status") == "FINALIZED"
            and item.get("execution") == "FINISHED_WITH_RETURN"
        )
        item["result"] = "FINALIZED_FINISHED_WITH_RETURN" if successful else (
            "FINALIZED_FINISHED_WITH_ERROR"
            if item.get("status") == "FINALIZED" else str(item.get("result_name") or item.get("consensus_result") or "FAILED")
        )
        item["children"] = result.get("children", [])
        if successful and readback is not None:
            read_address, read_method, read_args = readback
            item["readback"] = bridge.read(client, read_address, read_method, read_args)
        return item
    except Exception as error:
        item = _receipt_summary(_record(journal_obj, operation))
        item.update({
            "result": "FAILED",
            "exception": f"{type(error).__name__}: {error}",
        })
        return item


def _deploy(
    *, client: Any, journal_obj: Any, operation: str, source: Path, args: list[Any], name: str,
) -> tuple[str, dict[str, Any]]:
    result = _submit_diagnostic(
        client=client,
        journal_obj=journal_obj,
        operation=operation,
        kind="diagnostic-deploy",
        source=source,
        args=args,
        fee_metadata={"diagnostic_only": True, "contract_name": name, "emitted_child_messages": 0},
    )
    record = _record(journal_obj, operation)
    address = bridge._contract_address(result["receipt"])
    if not address:
        raise RuntimeError(f"{operation} returned no deployed contract address")
    return address, {
        "address": address,
        "tx_hash": result["tx_hash"],
        "result": "FINALIZED_FINISHED_WITH_RETURN",
        "receipt": _receipt_summary(record),
        "source_sha256": _sha(source),
        "source_length": len(source.read_bytes()),
    }


def _direct_target_read(client: Any, target: str) -> dict[str, Any]:
    return {
        "number": bridge.read(client, target, "get_number"),
        "text": bridge.read(client, target, "get_text"),
        "owner": bridge.read(client, target, "get_owner"),
    }


def main() -> int:
    if bridge.RPC != RPC or bridge.CHAIN_ID != CHAIN_ID or bridge.NETWORK != NETWORK:
        raise RuntimeError("stable probe bridge is not locked to Studionet 61999")
    client = bridge.make_client()
    journal_obj = bridge.journal()
    preflight = bridge.account_preflight(client, bridge.EXPECTED_DEPLOYER, journal_obj)
    if preflight["latest_nonce"] != preflight["pending_nonce"]:
        raise RuntimeError("latest and pending nonce differ before diagnostic writes")
    if preflight["unresolved_journal_operations"]:
        raise RuntimeError("unresolved diagnostic journal operations exist")

    result: dict[str, Any] = {
        "schema": "sentinelx-studionet-finalized-view-probe-v1",
        "diagnostic_only": True,
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "starting_head": _git_head(),
        "signer": bridge.EXPECTED_DEPLOYER,
        "preflight": preflight,
        "historical_profile": {
            "label": "STUDIONET_V22_PROFILE_FINALIZED_VIEW_INVESTIGATION",
            "governor": CURRENT_PROFILE_GOVERNOR,
            "upgraded_target": UPGRADED_PROFILE_TARGET,
            "writes_to_current_profile": False,
        },
        "runtime_support": {
            "typed_interface": True,
            "generic_get_at": True,
            "generic_api": "gl.get_contract_at",
            "note": "Stable py-genlayer v0.18 exposes get_contract_at; this is the stable equivalent of gl.contract.get_at.",
        },
        "source_files": {
            path.name: {"sha256": _sha(path), "bytes": len(path.read_bytes())}
            for path in (TARGET_SOURCE, TYPED_CALLER_SOURCE, SENTINELX_CALLER_SOURCE)
        },
    }

    minimal_target, target_deploy = _deploy(
        client=client, journal_obj=journal_obj, operation="probe.minimal.deploy_target",
        source=TARGET_SOURCE, args=[17, "finalized-view-probe"], name="FinalizedViewProbeTarget",
    )
    result["minimal_probe_target"] = minimal_target
    result["minimal_probe_target_deploy"] = target_deploy
    result["minimal_direct_read"] = _direct_target_read(client, minimal_target)

    typed_caller, caller_deploy = _deploy(
        client=client, journal_obj=journal_obj, operation="probe.minimal.deploy_typed_caller",
        source=TYPED_CALLER_SOURCE, args=[], name="FinalizedViewProbeCaller",
    )
    result["minimal_probe_caller"] = typed_caller
    result["minimal_probe_caller_deploy"] = caller_deploy
    result["minimal_default"] = _attempt(
        client=client, journal_obj=journal_obj, operation="probe.minimal.default",
        method="probe_default", address=typed_caller, args=[minimal_target],
        readback=(typed_caller, "get_last_number", []),
    )
    result["minimal_finalized"] = _attempt(
        client=client, journal_obj=journal_obj, operation="probe.minimal.latest_finalized",
        method="probe_latest_finalized", address=typed_caller, args=[minimal_target],
        readback=(typed_caller, "get_last_number", []),
    )
    result["minimal_decided"] = _attempt(
        client=client, journal_obj=journal_obj, operation="probe.minimal.latest_decided",
        method="probe_latest_decided", address=typed_caller, args=[minimal_target],
        readback=(typed_caller, "get_last_number", []),
    )

    sentinelx_caller, sentinelx_deploy = _deploy(
        client=client, journal_obj=journal_obj, operation="probe.sentinelx.deploy_caller",
        source=SENTINELX_CALLER_SOURCE, args=[], name="SentinelXViewProbeCaller",
    )
    result["sentinelx_probe_caller"] = sentinelx_caller
    result["sentinelx_probe_caller_deploy"] = sentinelx_deploy
    result["upgraded_target"] = UPGRADED_PROFILE_TARGET
    result["upgraded_default"] = _attempt(
        client=client, journal_obj=journal_obj, operation="probe.upgraded.default",
        method="probe_default_installed", address=sentinelx_caller, args=[UPGRADED_PROFILE_TARGET],
        readback=(sentinelx_caller, "get_last_installed", []),
    )
    result["upgraded_finalized"] = _attempt(
        client=client, journal_obj=journal_obj, operation="probe.upgraded.latest_finalized",
        method="probe_finalized_installed", address=sentinelx_caller, args=[UPGRADED_PROFILE_TARGET],
        readback=(sentinelx_caller, "get_last_installed", []),
    )
    result["upgraded_decided"] = _attempt(
        client=client, journal_obj=journal_obj, operation="probe.upgraded.latest_decided",
        method="probe_decided_installed", address=sentinelx_caller, args=[UPGRADED_PROFILE_TARGET],
        readback=(sentinelx_caller, "get_last_installed", []),
    )
    result["upgraded_get_at_finalized"] = _attempt(
        client=client, journal_obj=journal_obj, operation="probe.upgraded.get_at_finalized",
        method="probe_get_at_finalized_installed", address=sentinelx_caller, args=[UPGRADED_PROFILE_TARGET],
        readback=(sentinelx_caller, "get_last_installed", []),
    )

    baseline_target, baseline_deploy = _deploy(
        client=client, journal_obj=journal_obj, operation="probe.baseline.deploy_target",
        source=BASELINE_SOURCE,
        args=[CURRENT_PROFILE_GOVERNOR, "SentinelX baseline finalized-view probe", "probe baseline value"],
        name="ProtectedApplication baseline diagnostic target",
    )
    result["fresh_baseline_target"] = baseline_target
    result["fresh_baseline_target_deploy"] = baseline_deploy
    result["baseline_external_installed_read"] = {
        "proposal_id": bridge.read(client, baseline_target, "get_installed_proposal_id"),
        "candidate_hash": bridge.read(client, baseline_target, "get_installed_candidate_hash"),
    }
    result["baseline_default"] = _attempt(
        client=client, journal_obj=journal_obj, operation="probe.baseline.default",
        method="probe_default_installed", address=sentinelx_caller, args=[baseline_target],
        readback=(sentinelx_caller, "get_last_installed", []),
    )
    result["baseline_finalized"] = _attempt(
        client=client, journal_obj=journal_obj, operation="probe.baseline.latest_finalized",
        method="probe_finalized_installed", address=sentinelx_caller, args=[baseline_target],
        readback=(sentinelx_caller, "get_last_installed", []),
    )
    result["baseline_decided"] = _attempt(
        client=client, journal_obj=journal_obj, operation="probe.baseline.latest_decided",
        method="probe_decided_installed", address=sentinelx_caller, args=[baseline_target],
        readback=(sentinelx_caller, "get_last_installed", []),
    )

    result["ending_preflight"] = bridge.account_preflight(client, bridge.EXPECTED_DEPLOYER, journal_obj)
    result["ending_head"] = _git_head()
    result["journal_path"] = str(bridge.JOURNAL_PATH)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
