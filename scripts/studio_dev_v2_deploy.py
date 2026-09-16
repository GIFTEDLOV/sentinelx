"""Fail-closed future V2 canonical deployment workflow.

This command is a source/deployment gate, not a deployment performed by
Phase 2F. It defaults to read-only manifest verification. Broadcasting is
available only behind two explicit controls and always persists the returned
transaction hash before any polling.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RPC = "https://studio-dev.genlayer.com/api"
CHAIN_ID = 61997
MANIFEST = ROOT / "deployments" / "v2.1" / "SOURCE_MANIFEST.json"
JOURNAL = ROOT / "artifacts" / "studio-dev-v2-canonical-transactions.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def source_gate() -> dict[str, Any]:
    from scripts.v2_source_manifest import verify_manifest

    errors = verify_manifest()
    if errors:
        raise RuntimeError("V2 source manifest mismatch: " + "; ".join(errors))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["rpc"] != RPC or manifest["chain_id"] != CHAIN_ID:
        raise RuntimeError("canonical deployment requires Studio-dev chain 61997")
    return manifest


def assert_studio_dev_client(client: Any) -> None:
    chain = getattr(client, "chain", None)
    if getattr(chain, "id", None) != CHAIN_ID:
        raise RuntimeError("deployment client is not connected to Studio-dev chain 61997")
    rpc_urls = getattr(chain, "rpc_urls", {})
    try:
        rpc = rpc_urls["default"]["http"][0]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("deployment client does not expose the expected Studio-dev RPC") from error
    if rpc != RPC:
        raise RuntimeError("deployment client RPC is not https://studio-dev.genlayer.com/api")


def _hash_text(value: Any) -> str:
    text = value.hex() if isinstance(value, bytes) else str(value)
    if not text.startswith("0x"):
        text = "0x" + text
    if len(text) != 66 or any(char not in "0123456789abcdefABCDEF" for char in text[2:]):
        raise RuntimeError("SDK returned an invalid transaction hash")
    return text.lower()


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _execution(receipt: dict[str, Any]) -> str:
    return str(receipt.get("tx_execution_result_name") or receipt.get("txExecutionResultName") or "")


def _address(receipt: dict[str, Any]) -> str:
    value = receipt.get("contract_address") or receipt.get("contractAddress")
    if not value:
        raise RuntimeError("deployment receipt did not contain a contract address")
    return str(value)


def preflight_only() -> dict[str, Any]:
    manifest = source_gate()
    return {
        "ok": True,
        "broadcast": False,
        "network": "studio-dev",
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "manifest": str(MANIFEST),
        "contracts": manifest["contracts"],
    }


def deploy_once(*, client: Any, account: Any, source: bytes, source_path: Path,
                deployed_source_dump: Path, operation: str) -> dict[str, Any]:
    """Estimate, reserve, broadcast once, and prove finalized deployment."""
    manifest = source_gate()
    assert_studio_dev_client(client)
    if source != source_path.read_bytes():
        raise RuntimeError("deployment source bytes changed after manifest verification")
    expected = next(record["sha256"] for record in manifest["contracts"] if record["path"] == str(source_path.relative_to(ROOT)).replace("\\", "/"))
    address = client.w3.to_checksum_address(account.address)
    latest = int(client.get_current_nonce(address, "latest"))
    pending = int(client.get_transaction_count(address, "pending"))
    if latest != pending:
        raise RuntimeError("unknown pending activity; deployment is blocked")
    estimate = client.estimate_transaction_fees()
    if "distribution" not in estimate or "feeValue" not in estimate:
        raise RuntimeError("SDK deployment estimate is incomplete")
    from scripts.transaction_journal import TransactionJournal

    journal = TransactionJournal(JOURNAL)
    journal.reserve_broadcast(
        operation, network="studio-dev", rpc=RPC, chain_id=CHAIN_ID,
        contract_version="SentinelX V2", source_manifest=str(MANIFEST),
    )
    try:
        returned = client.deploy_contract(
            source, account=account, args=[], fees=estimate,
            consensus_max_rotations=client.chain.default_consensus_max_rotations,
        )
    except Exception as error:
        journal.update(operation, state="BROADCAST_CALL_RAISED", broadcast_error=str(error))
        raise RuntimeError("broadcast outcome is ambiguous; reconcile the reserved operation") from error
    tx_hash = _hash_text(returned)
    journal.record_submission(operation, tx_hash)
    receipt = client.wait_for_transaction_receipt(tx_hash, wait_until="finalized", full_transaction=True)
    lifecycle = client.get_transaction_lifecycle(tx_hash)
    stored = _enum_text(lifecycle.get("stored_status_name"))
    execution = _execution(receipt)
    if stored != "Finalized" or execution != "FINISHED_WITH_RETURN":
        journal.update(operation, state="FINALIZED_EXECUTION_FAILED", lifecycle=lifecycle, execution_result=execution)
        raise RuntimeError("deployment did not reach Finalized + FINISHED_WITH_RETURN")
    deployed_address = _address(receipt)
    from scripts.verify_deployed_source import verify

    parity = verify(source_path, deployed_source_dump, expected_sha256=str(expected))
    if not parity["parity"]:
        raise RuntimeError("deployed source/code parity check failed")
    info = client.read_contract(deployed_address, "contract_info", args=[])
    if not isinstance(info, str) or "sentinelx-governor-v2" not in info:
        raise RuntimeError("deployed contract_info did not prove SentinelX V2")
    journal.update(
        operation, state="FINALIZED_EXECUTED", lifecycle=lifecycle,
        execution_result=execution, address=deployed_address,
        contract_info=info, source_parity=parity,
    )
    return {"tx_hash": tx_hash, "address": deployed_address, "contract_info": info}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broadcast", action="store_true", help="enable the future write workflow")
    args = parser.parse_args()
    if not args.broadcast:
        print(json.dumps(preflight_only(), indent=2, sort_keys=True))
        return 0
    if os.environ.get("SENTINELX_ALLOW_BROADCAST") != "1":
        raise SystemExit("--broadcast requires SENTINELX_ALLOW_BROADCAST=1")
    raise SystemExit("canonical V2 deployment requires an operator-selected account and is not run by Phase 2F")


if __name__ == "__main__":
    raise SystemExit(main())
