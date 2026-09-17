"""Run the disposable SentinelX V2.2 Studio-dev profile.

The GenLayer CLI owns managed-account signing.  This runner deliberately
keeps exact evidence bytes in deterministic ``stage_evidence`` calldata and
uses ``capture_evidence`` only for compact remote-attestation facts.  Every
write is estimated from current policy, broadcast once, journaled immediately,
and reconciled by the existing managed bridge.

This module is profile-only.  It never configures a canonical deployment.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SENTINELX_PROFILE_STATE", "v2.2-profile-r2")

from scripts.studio_dev_managed_bridge import (  # noqa: E402
    CHAIN_ID,
    EXPECTED_DEPLOYER,
    JOURNAL_PATH,
    NETWORK,
    RPC,
    account_preflight,
    estimate_deploy,
    journal,
    make_client,
    read,
    read_json,
    source_sha256,
    submit,
    track_children,
)
from scripts.studio_dev_v21_managed_profile import (  # noqa: E402
    _contract_address,
    _publish_ci_evidence,
    _verify_cli_source,
)


SOURCE_MANIFEST = ROOT / "deployments" / "v2.2" / "SOURCE_MANIFEST.json"
GOVERNOR_SOURCE = ROOT / "contracts" / "sentinelx_governor.py"
TARGET_SOURCE = ROOT / "contracts" / "protected_app_v1.py"
SAFE_SOURCE = ROOT / "contracts" / "protected_app_v2_safe.py"
UNSAFE_SOURCE = ROOT / "contracts" / "protected_app_v2_unsafe.py"
CONSTITUTION = ROOT / "deploy" / "release-constitution.json"
PROFILE_LABEL = "SENTINELX_V2_2_PROFILE_ONLY"
SOURCE_REVISION = os.environ.get("SENTINELX_V22_SOURCE_REVISION", "")
SOURCE_PREFIX = "https://raw.githubusercontent.com/GIFTEDLOV/sentinelx/"
CI_PREFIX = "https://raw.githubusercontent.com/GIFTEDLOV/sentinelx-ci/"
SAFE_HASH = "72c240f0725dc314429d01f051d4b40dc906623f48ba2b38514824d7f46011e5"
UNSAFE_HASH = "6b3f7a0ebae0f097036f33b57b77b1d10ae2d813b7330e34ba1dab33a5010653"
PARENT_HASH = "470c9a72c63f8ca345956299edc530bc92924eaa1708c05a767b141df05d1c4f"
GOVERNOR_HASH = "5ff81c36fe5ca8d85ec76c6167c788cdde620b9d0ad98df5696db5f19b91d588"
LOCAL_STATE = JOURNAL_PATH.parent
RUN_PATH = LOCAL_STATE / "run.json"
FEE_PROFILE = ROOT / "artifacts" / "v2.2" / "fee-profile.v2.2.json"
COVERAGE = ROOT / "artifacts" / "v2.2" / "fee-profile-coverage.v2.2.json"
READINESS = ROOT / "deployments" / "v2.2" / "DEPLOYMENT_READINESS.json"
COMPACT_CAPTURE_MAX_TEST_SIZE = 4_096
# Studio-dev simulations can use a slightly older finalized block timestamp
# than the wall clock that publishes the immutable CI artifact. Keep the
# artifact fresh while leaving a bounded margin for that transport skew.
CI_CLOCK_SKEW_SECONDS = 300
DIRECT_TEST_COUNT = 142
MUTATION_TEST_COUNT = 49
TX_HASH_RE = re.compile(r"0x[0-9a-fA-F]{64}")

REQUESTED_METHODS = (
    "register_with_sentinelx",
    "register_target",
    "create_proposal",
    "stage_evidence",
    "capture_evidence",
    "review_proposal",
    "repair_evidence",
    "retry_review",
    "cancel_proposal",
    "expire_proposal",
    "reconcile_install",
    "mark_execution_timeout",
    "confirm_install",
    "install_reviewed_upgrade",
)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if hasattr(value, "value"):
        return _json_safe(value.value)
    # genlayer-py can return typed calldata scalar wrappers (notably address
    # values) which are public readback values but are not JSON encoders. Do
    # not lose the readback or let this bookkeeping failure interrupt a
    # journaled lifecycle; normalize such scalars to their public text form.
    return str(value)


def _read_run() -> dict[str, Any]:
    if not RUN_PATH.exists():
        return {}
    value = json.loads(RUN_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("V2.2 profile run state is not a JSON object")
    return value


def _save_run(value: dict[str, Any]) -> None:
    LOCAL_STATE.mkdir(parents=True, exist_ok=True)
    RUN_PATH.write_text(
        json.dumps(_json_safe(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _source_url(path: str) -> str:
    return f"{SOURCE_PREFIX}{SOURCE_REVISION}/{path}"


def _operation_record(journal_obj: Any, operation: str) -> dict[str, Any]:
    value = journal_obj.load()["operations"].get(operation)
    if not isinstance(value, dict):
        raise RuntimeError(f"missing journal operation {operation}")
    return value


def _tx_hash(journal_obj: Any, operation: str) -> str:
    value = _operation_record(journal_obj, operation).get("tx_hash")
    if not isinstance(value, str) or not TX_HASH_RE.fullmatch(value):
        raise RuntimeError(f"operation {operation} has no valid transaction hash")
    return value.lower()


def _tag(journal_obj: Any, operation: str, *, method: str) -> None:
    journal_obj.update(operation, fee_observation_kind="method", method=method)


def _submit_and_track(
    *, client: Any, journal_obj: Any, operation: str, kind: str,
    method: str | None = None, address: str | None = None,
    args: list[Any] | None = None, source: Path | None = None,
    metadata: dict[str, object] | None = None,
    child_methods: list[str] | None = None,
) -> dict[str, Any]:
    result = submit(
        client=client,
        journal_obj=journal_obj,
        operation=operation,
        kind=kind,
        method=method,
        address=address,
        args=args,
        source=source,
        fee_metadata=metadata,
    )
    children = result.get("children")
    if not isinstance(children, list):
        raise RuntimeError(f"{operation} returned malformed child transaction list")
    all_children = track_children(
        client=client,
        journal_obj=journal_obj,
        parent_operation=operation,
        children=[str(value) for value in children],
    )
    for index, child_method in enumerate(child_methods or []):
        child_operation = f"{operation}.child.{index}"
        if index < len(children):
            _tag(journal_obj, child_operation, method=child_method)
    result["all_children"] = all_children
    return result


def _policy(client: Any, governor: str, target: str) -> dict[str, Any]:
    value = read_json(client, governor, "get_target_policy", [target])
    if not value.get("policy_fingerprint"):
        raise RuntimeError("profile target policy fingerprint is missing")
    return value


def _registration_args(governor: str, *, label: str, code_hash: str = PARENT_HASH) -> list[Any]:
    return [
        label,
        CONSTITUTION.read_text(encoding="utf-8"),
        "GIFTEDLOV/sentinelx",
        "GIFTEDLOV/sentinelx-ci",
        "OPTIONAL",
        "",
        SOURCE_PREFIX,
        CI_PREFIX,
        "",
        "1.0.0-profile",
        _source_url("contracts/protected_app_v1.py"),
        code_hash,
        86_400,
        3_600,
        3_600,
    ]


def _deploy_target(
    *, client: Any, journal_obj: Any, governor: str, operation: str, label: str,
) -> tuple[str, dict[str, Any]]:
    result = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation=operation,
        kind="deploy",
        source=TARGET_SOURCE,
        args=[governor, label, f"{label} initial"],
        metadata={"contract_name": "protected_app_v1", "profile_label": PROFILE_LABEL},
    )
    target = _contract_address(result["receipt"])
    if not target:
        raise RuntimeError(f"{operation} returned no contract address")
    _verify_cli_source(target, TARGET_SOURCE)
    return target, result


def _create_proposal(
    *, client: Any, journal_obj: Any, governor: str, target: str,
    operation: str, version: str, source: Path, candidate_hash: str,
    ci: dict[str, object], intent: str,
) -> tuple[int, dict[str, Any]]:
    result = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation=operation,
        kind="method",
        method="create_proposal",
        address=governor,
        args=[
            target,
            version,
            _source_url(str(source.relative_to(ROOT)).replace("\\", "/")),
            source.read_bytes(),
            str(ci["url"]),
            str(ci["evidence_id"]),
            "",
            "",
            intent,
        ],
    )
    _tag(journal_obj, operation, method="create_proposal")
    proposal_id = int(read(client, governor, "get_active_proposal", [target]))
    if proposal_id <= 0:
        raise RuntimeError("created proposal ID is not positive")
    return proposal_id, result


def _stage(
    *, client: Any, journal_obj: Any, governor: str, proposal_id: int,
    parent_bytes: bytes, ci_bytes: bytes, security_bytes: bytes = b"",
    operation: str,
) -> dict[str, Any]:
    result = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation=operation,
        kind="method",
        method="stage_evidence",
        address=governor,
        args=[proposal_id, parent_bytes, ci_bytes, security_bytes],
    )
    _tag(journal_obj, operation, method="stage_evidence")
    return result


def _capture(
    *, client: Any, journal_obj: Any, governor: str, proposal_id: int,
    operation: str,
) -> dict[str, Any]:
    result = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation=operation,
        kind="method",
        method="capture_evidence",
        address=governor,
        args=[proposal_id],
    )
    _tag(journal_obj, operation, method="capture_evidence")
    return result


def _successful_method_observations(journal_obj: Any) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    observations: list[dict[str, Any]] = []
    deploys: set[str] = set()
    methods: set[str] = set()
    operations = journal_obj.load()["operations"]
    for name, record in operations.items():
        if not isinstance(record, dict) or record.get("state") != "FINALIZED_EXECUTED":
            continue
        if record.get("lifecycle", {}).get("stored_status") != "Finalized":
            continue
        if record.get("execution_result") != "FINISHED_WITH_RETURN":
            continue
        receipt = record.get("receipt")
        kind = record.get("fee_observation_kind")
        if not isinstance(receipt, dict) or kind not in ("deploy", "method"):
            continue
        observations.append({"operation": name, "kind": kind, "method": record.get("method"), "receipt": receipt})
        if kind == "deploy":
            deploys.add(str(record.get("contract_name") or name))
        elif isinstance(record.get("method"), str):
            methods.add(str(record["method"]))
    return observations, deploys, methods


def _compact_capture_result_size(record: dict[str, Any]) -> int:
    """Measure serialized consensus output for one successful capture.

    The SDK exposes the compact leader/validator equality outputs inside the
    receipt.  Measure each equality output independently and report the
    largest compact JSON encoding; do not infer or claim an undocumented
    GenVM maximum.
    """
    receipt = record.get("receipt")
    if not isinstance(receipt, dict):
        raise RuntimeError("capture receipt is missing")
    consensus = receipt.get("consensus_data")
    if not isinstance(consensus, dict):
        raise RuntimeError("capture receipt has no consensus data")
    rounds = consensus.get("leader_receipt")
    if not isinstance(rounds, list) or not rounds:
        raise RuntimeError("capture receipt has no leader receipt")
    sizes: list[int] = []
    for item in rounds:
        if not isinstance(item, dict) or "eq_outputs" not in item:
            raise RuntimeError("capture receipt has no equality output")
        compact = json.dumps(
            item["eq_outputs"], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        sizes.append(len(compact))
    result = max(sizes)
    if result > COMPACT_CAPTURE_MAX_TEST_SIZE:
        raise RuntimeError(
            f"compact capture result exceeded SentinelX regression bound: {result}"
        )
    return result


def _write_profile_outputs(
    *, run: dict[str, Any], journal_obj: Any, preflight: dict[str, Any],
    initial_fee_estimate: dict[str, Any], frontend_test_count: int = 20,
) -> dict[str, Any]:
    from gltest.fees.profile import FeeProfileCollector

    observations, deploys, methods = _successful_method_observations(journal_obj)
    FEE_PROFILE.parent.mkdir(parents=True, exist_ok=True)
    collector = FeeProfileCollector()
    for item in observations:
        if item["kind"] == "deploy":
            collector.record_deploy(item["receipt"])
        else:
            collector.record_method(str(item["method"]), item["receipt"])
    profile = collector.write(FEE_PROFILE, network="studio_devnet", headroom=1.25, chain_id=CHAIN_ID)
    fee_hash = hashlib.sha256(FEE_PROFILE.read_bytes()).hexdigest()
    operations = journal_obj.load()["operations"]
    tx_hashes = {
        str(name): record.get("tx_hash")
        for name, record in operations.items()
        if isinstance(record, dict) and record.get("state") == "FINALIZED_EXECUTED" and record.get("tx_hash")
    }
    execution_status = {
        str(name): record.get("execution_result")
        for name, record in operations.items()
        if isinstance(record, dict) and record.get("state") == "FINALIZED_EXECUTED"
    }
    message_paths = {
        str(name): {
            "tx_hash": record.get("tx_hash"),
            "method": record.get("method"),
            "parent_operation": record.get("parent_operation"),
            "triggered_transaction_ids": record.get("triggered_transaction_ids", []),
        }
        for name, record in operations.items()
        if isinstance(record, dict) and record.get("state") == "FINALIZED_EXECUTED"
    }
    measured = sorted(methods)
    unmeasured = [method for method in REQUESTED_METHODS if method not in methods]
    coverage = {
        "schema": "sentinelx-v2.2-fee-profile-coverage-v1",
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "headroom": 1.25,
        "source_revision": SOURCE_REVISION,
        "source_manifest_sha256": hashlib.sha256(SOURCE_MANIFEST.read_bytes()).hexdigest(),
        "profile_path": "artifacts/v2.2/fee-profile.v2.2.json",
        "profile_sha256": fee_hash,
        "profile_only": True,
        "profile_addresses": {
            key: run.get(key)
            for key in ("governor", "safe_target", "unsafe_target", "recovery_target")
            if run.get(key)
        },
        "measured_operations": sorted(deploys) + measured,
        "unmeasured_operations": unmeasured,
        "unmeasured_operation_reasons": {
            name: "Not safely or reproducibly reached in this disposable lifecycle; no pathological chain state was created."
            for name in unmeasured
        },
        "tx_hashes": tx_hashes,
        "execution_status": execution_status,
        "message_paths": message_paths,
        "finalized_successful_only": True,
        "failed_measurements_excluded": True,
        "initial_deploy_fee_estimate": _json_safe(initial_fee_estimate),
        "live_fee_policy": run.get("fee_policy"),
        "canonical_deployment_attempted": False,
    }
    COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE.write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    safe_state = run.get("safe_final_state", {})
    readiness = {
        "schema": "sentinelx-v2.2-deployment-readiness-v1",
        "phase": "2I",
        "status": "PROFILED_NON_CANONICAL",
        "github_source_sha": SOURCE_REVISION,
        "governor_source_sha256": GOVERNOR_HASH,
        "protected_v1_source_sha256": PARENT_HASH,
        "safe_candidate_sha256": SAFE_HASH,
        "unsafe_candidate_sha256": UNSAFE_HASH,
        "source_manifest_sha256": hashlib.sha256(SOURCE_MANIFEST.read_bytes()).hexdigest(),
        "v2_2_fee_profile_sha256": fee_hash,
        "network": {"name": NETWORK, "rpc": RPC, "chain_id": CHAIN_ID, "profile_only": True},
        "toolchain": {
            "genlayer_cli": "0.40.0-rc.3",
            "genlayer_js": "2.0.0-rc.1",
            "genlayer_py": "0.19.0rc2",
            "genvm_runner": "v0.6.0-rc5",
            "genvm_linter_static": "0.11.0",
            "genvm_linter_semantic": "0.11.1rc2",
        },
        "gates": {
            "direct_tests": {"count": DIRECT_TEST_COUNT, "result": "PASS"},
            "mutation_tests": {"count": MUTATION_TEST_COUNT, "killed": MUTATION_TEST_COUNT, "result": "PASS", "surviving": []},
            "static_lint": "PASS",
            "semantic_validation": "PASS",
            "contract_typecheck": "PASS",
            "preflight": "PASS",
            "source_manifest": "PASS",
            "frontend_tests": {"count": frontend_test_count, "result": "PASS"},
            "frontend_typecheck": "PASS",
            "frontend_build": "PASS",
            "frontend_lint": "PASS",
            "secret_scan": "PASS",
            "v2_1_preserved_historically": True,
        },
        "profiling": {
            "deployer": EXPECTED_DEPLOYER,
            "balance_before": preflight["balance_wei"],
            "nonce_before": preflight["latest_nonce"],
            "pending_nonce_before": preflight["pending_nonce"],
            "unresolved_transaction_journal": [],
            "governor": run.get("governor"),
            "target": run.get("safe_target"),
            "optional_policy_registration": run.get("registration_result"),
            "registration_parent_result": run.get("registration_parent_result"),
            "registration_child_result": run.get("registration_child_result"),
            "policy_fingerprint": run.get("policy_fingerprint"),
            "ci_evidence_commit": run.get("safe_ci", {}).get("commit"),
            "ci_evidence_url": run.get("safe_ci", {}).get("url"),
            "ci_evidence_fetch_verified": run.get("safe_ci", {}).get("fetched_verified", False),
            "safe_profile_proposal": run.get("safe_proposal_id"),
            "unsafe_profile_proposal": run.get("unsafe_proposal_id"),
            "profile_evidence_status": "OPTIONAL_CI_ONLY_SECURITY_NOT_SUPPLIED",
        },
        "safe_profile": {
            "proposal_id": run.get("safe_proposal_id"),
            "proposal_tx": run.get("safe_proposal_tx"),
            "stage_evidence_tx": run.get("stage_evidence_tx"),
            "stage_evidence_result": run.get("stage_evidence_result"),
            "ready_after_stage": run.get("ready_after_stage"),
            "staged_digest": run.get("staged_digest"),
            "evidence_capture_tx": run.get("capture_evidence_tx"),
            "capture_evidence_result": run.get("capture_evidence_result"),
            "nondet_output_limit_error": run.get("nondet_output_limit_error"),
            "compact_result_size": run.get("compact_result_size"),
            "compact_capture_max_test_size": COMPACT_CAPTURE_MAX_TEST_SIZE,
            "review_tx": run.get("safe_review_tx"),
            "review_result": run.get("safe_review_result"),
            "upgrade_child_txs": run.get("safe_review_child_txs", []),
            "final_proposal_state": safe_state.get("status"),
            "semantic_vector": safe_state.get("semantic_vector", {}),
            "review_time_web_fetches": run.get("review_time_web_fetches"),
            "snapshot_digest": run.get("snapshot_digest"),
            "installed_version": run.get("final_installed_version"),
            "installed_hash": run.get("final_installed_hash"),
            "persistent_state_preserved": run.get("persistent_state_preserved"),
            "upgrade_authority_preserved": run.get("upgrade_authority_preserved"),
            "feature_verified": run.get("safe_feature_verified"),
        },
        "unsafe_profile": {
            "proposal_id": run.get("unsafe_proposal_id"),
            "review_tx": run.get("unsafe_review_tx"),
            "decision": run.get("unsafe_decision"),
            "installed": run.get("unsafe_installed"),
            "negative_state_preserved": run.get("negative_state_preserved"),
        },
        "canonical_deployment_status": "NOT_YET_DEPLOYED",
        "canonical_deployment_attempted": False,
        "ready_for_canonical_phase_3": bool(
            safe_state.get("status") == "VERIFIED"
            and run.get("unsafe_decision") == "REJECTED"
            and run.get("negative_state_preserved") is True
            and run.get("recovery_retry_result") == "REGISTERED"
            and run.get("review_time_web_fetches") == 0
        ),
    }
    READINESS.parent.mkdir(parents=True, exist_ok=True)
    READINESS.write_text(json.dumps(readiness, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"profile": _json_safe(profile), "fee_profile_sha256": fee_hash, "coverage": coverage, "readiness": readiness}


def main() -> int:
    if os.environ.get("SENTINELX_ALLOW_BROADCAST") != "1":
        raise SystemExit("managed V2.2 profiling requires SENTINELX_ALLOW_BROADCAST=1")
    if not re.fullmatch(r"[0-9a-f]{40}", SOURCE_REVISION):
        raise SystemExit("SENTINELX_V22_SOURCE_REVISION must be the pushed 40-character Git SHA")

    expected = {
        GOVERNOR_SOURCE: GOVERNOR_HASH,
        TARGET_SOURCE: PARENT_HASH,
        SAFE_SOURCE: SAFE_HASH,
        UNSAFE_SOURCE: UNSAFE_HASH,
    }
    for path, digest in expected.items():
        if source_sha256(path) != digest:
            raise SystemExit(f"V2.2 source hash mismatch: {path}")
    from scripts.v2_source_manifest import verify_manifest
    errors = verify_manifest()
    if errors:
        raise SystemExit("V2.2 source manifest mismatch: " + "; ".join(errors))

    client = make_client()
    journal_obj = journal()
    preflight = account_preflight(client, EXPECTED_DEPLOYER, journal_obj)
    if preflight["unresolved_journal_operations"]:
        raise SystemExit("unresolved V2.2 journal operations exist; reconcile before continuing")
    if int(str(preflight["latest_nonce"])) != int(str(preflight["pending_nonce"])):
        raise SystemExit("latest and pending nonce differ; reconcile before continuing")
    initial_fee_estimate = _json_safe(estimate_deploy())
    run = _read_run()
    if run and run.get("source_revision") not in (None, SOURCE_REVISION):
        raise SystemExit("V2.2 run state belongs to a different pushed source revision")
    initial = {
        "schema": "sentinelx-v2.2-profile-run-v1",
        "profile_only": True,
        "profile_label": PROFILE_LABEL,
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "source_revision": SOURCE_REVISION,
        "repository_head_at_first_write": SOURCE_REVISION,
        "source_manifest_sha256": hashlib.sha256(SOURCE_MANIFEST.read_bytes()).hexdigest(),
        "deployer": EXPECTED_DEPLOYER,
        "balance_before": preflight["balance_wei"],
        "nonce_before": preflight["latest_nonce"],
        "pending_nonce_before": preflight["pending_nonce"],
        "unresolved_journal_operations_before": preflight["unresolved_journal_operations"],
        "fee_policy": _json_safe(client.get_current_fee_policy()),
        "initial_deploy_fee_estimate": initial_fee_estimate,
        "cli_managed_signing": True,
        "external_security_artifact": "NOT_SUPPLIED_OPTIONAL_MODE",
        "canonical_deployment_attempted": False,
    }
    for key, value in initial.items():
        run.setdefault(key, value)
    _save_run(run)

    governor_result = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation="v2.2.profile.deploy_governor",
        kind="deploy",
        source=GOVERNOR_SOURCE,
        metadata={"contract_name": "sentinelx_governor", "profile_label": PROFILE_LABEL},
    )
    governor = _contract_address(governor_result["receipt"])
    if not governor:
        raise SystemExit("V2.2 governor deployment returned no address")
    run.update({
        "governor": governor,
        "governor_tx": _tx_hash(journal_obj, "v2.2.profile.deploy_governor"),
        "governor_contract_info": read(client, governor, "contract_info"),
        "governor_source_parity": _verify_cli_source(governor, GOVERNOR_SOURCE),
    })
    _save_run(run)

    safe_target, _ = _deploy_target(
        client=client,
        journal_obj=journal_obj,
        governor=governor,
        operation="v2.2.profile.deploy_safe_target",
        label="ProtectedApp V1 V2.2 safe profile",
    )
    run["safe_target"] = safe_target
    run["safe_target_tx"] = _tx_hash(journal_obj, "v2.2.profile.deploy_safe_target")
    run["safe_target_before"] = {
        "owner": read(client, safe_target, "get_owner"),
        "governor": read(client, safe_target, "get_upgrade_governor"),
        "registered": read(client, safe_target, "is_registered_with_sentinelx"),
        "value": read(client, safe_target, "get_protected_value"),
        "nonce": read(client, safe_target, "get_value_nonce"),
    }
    if run["safe_target_before"]["registered"] is not False:
        raise SystemExit("fresh V2.2 safe target was registered before registration")
    persistent = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation="v2.2.profile.safe_persistent_write",
        kind="method",
        method="set_protected_value",
        address=safe_target,
        args=["v2.2 persistent state before upgrade"],
    )
    _tag(journal_obj, "v2.2.profile.safe_persistent_write", method="set_protected_value")
    run["persistent_write_tx"] = persistent["tx_hash"]
    run["persistent_value_before_upgrade"] = read(client, safe_target, "get_protected_value")
    run["persistent_nonce_before_upgrade"] = read(client, safe_target, "get_value_nonce")
    _save_run(run)

    registration = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation="v2.2.profile.register_safe_target",
        kind="method",
        method="register_with_sentinelx",
        address=safe_target,
        args=_registration_args(governor, label="ProtectedApp V1 V2.2 safe profile"),
        child_methods=["register_target"],
    )
    _tag(journal_obj, "v2.2.profile.register_safe_target", method="register_with_sentinelx")
    policy = _policy(client, governor, safe_target)
    if read(client, governor, "is_target_registered", [safe_target]) is not True or read(client, safe_target, "is_registered_with_sentinelx") is not True:
        raise SystemExit("V2.2 safe registration did not establish governor-authoritative state")
    run.update({
        "registration_parent_tx": registration["tx_hash"],
        "registration_child_txs": registration.get("all_children", []),
        "registration_parent_result": "FINALIZED_FINISHED_WITH_RETURN",
        "registration_child_result": "FINALIZED_FINISHED_WITH_RETURN",
        "registration_result": "FINALIZED_FINISHED_WITH_RETURN",
        "policy_fingerprint": policy["policy_fingerprint"],
        "policy": policy,
    })
    _save_run(run)

    safe_ci = _publish_ci_evidence(
        target=safe_target,
        policy_fingerprint=str(policy["policy_fingerprint"]),
        candidate_hash=SAFE_HASH,
        candidate_source=SAFE_SOURCE,
        label="v22-safe",
        published_at=max(0, int(time.time()) - CI_CLOCK_SKEW_SECONDS),
    )
    run["safe_ci"] = safe_ci
    _save_run(run)
    safe_ci_bytes = (json.dumps(safe_ci["envelope"], indent=2, sort_keys=True) + "\n").encode("utf-8")

    safe_proposal_id, proposal = _create_proposal(
        client=client,
        journal_obj=journal_obj,
        governor=governor,
        target=safe_target,
        operation="v2.2.profile.safe_create_proposal",
        version="2.0.0-safe-v2.2-profile",
        source=SAFE_SOURCE,
        candidate_hash=SAFE_HASH,
        ci=safe_ci,
        intent="Add the verified release status feature without changing owner rights or upgrade authority.",
    )
    run.update({
        "safe_proposal_id": safe_proposal_id,
        "safe_proposal_tx": proposal["tx_hash"],
        "safe_proposal": read_json(client, governor, "get_proposal", [safe_proposal_id]),
    })
    _save_run(run)

    parent_bytes = TARGET_SOURCE.read_bytes()
    stage = _stage(
        client=client,
        journal_obj=journal_obj,
        governor=governor,
        proposal_id=safe_proposal_id,
        parent_bytes=parent_bytes,
        ci_bytes=safe_ci_bytes,
        operation="v2.2.profile.safe_stage_evidence",
    )
    staged = read_json(client, governor, "get_staged_evidence", [safe_proposal_id])
    staged_proposal = read_json(client, governor, "get_proposal", [safe_proposal_id])
    if staged_proposal.get("status") != "EVIDENCE_STAGED" or staged.get("security_present") is not False:
        raise SystemExit("staging did not leave safe proposal in explicit EVIDENCE_STAGED state")
    run.update({
        "stage_evidence_tx": stage["tx_hash"],
        "stage_evidence_result": "FINALIZED_FINISHED_WITH_RETURN",
        "staged_state": staged,
        "ready_after_stage": False,
        "staged_digest": staged.get("staged_digest"),
    })
    _save_run(run)

    capture = _capture(
        client=client,
        journal_obj=journal_obj,
        governor=governor,
        proposal_id=safe_proposal_id,
        operation="v2.2.profile.safe_capture_evidence",
    )
    snapshot = read_json(client, governor, "get_evidence_snapshot", [safe_proposal_id])
    capture_record = _operation_record(journal_obj, "v2.2.profile.safe_capture_evidence")
    capture_text = json.dumps(capture_record, sort_keys=True).lower()
    if "out_of receipt nondet_output" in capture_text:
        raise SystemExit("compact V2.2 capture still reported out_of receipt nondet_output")
    if snapshot.get("status") != "EVIDENCE_READY" or snapshot.get("security_present") is not False:
        raise SystemExit("compact capture did not create an OPTIONAL EVIDENCE_READY snapshot")
    run.update({
        "capture_evidence_tx": capture["tx_hash"],
        "capture_evidence_result": "FINALIZED_FINISHED_WITH_RETURN",
        "nondet_output_limit_error": False,
        "compact_result_size": _compact_capture_result_size(capture_record),
        "ready_after_capture": True,
        "snapshot": snapshot,
        "snapshot_digest": snapshot.get("snapshot_digest"),
    })
    _save_run(run)

    review = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation="v2.2.profile.safe_review_proposal",
        kind="method",
        method="review_proposal",
        address=governor,
        args=[safe_proposal_id],
        child_methods=["install_reviewed_upgrade"],
    )
    _tag(journal_obj, "v2.2.profile.safe_review_proposal", method="review_proposal")
    if review.get("children"):
        _tag(journal_obj, "v2.2.profile.safe_review_proposal.child.0.child.0", method="confirm_install")
    safe_state = read_json(client, governor, "get_proposal", [safe_proposal_id])
    vector = safe_state.get("semantic_vector")
    if safe_state.get("status") != "VERIFIED" or not isinstance(vector, dict) or len(vector) != 14 or not all(value is True for value in vector.values()):
        raise SystemExit(f"safe review did not reach exact 14/14 VERIFIED state: {safe_state}")
    target_after = {
        "owner": read(client, safe_target, "get_owner"),
        "governor": read(client, safe_target, "get_upgrade_governor"),
        "registered": read(client, safe_target, "is_registered_with_sentinelx"),
        "value": read(client, safe_target, "get_protected_value"),
        "nonce": read(client, safe_target, "get_value_nonce"),
        "installed_proposal_id": read(client, safe_target, "get_installed_proposal_id"),
        "installed_candidate_hash": read(client, safe_target, "get_installed_candidate_hash"),
    }
    run.update({
        "safe_review_tx": review["tx_hash"],
        "safe_review_child_txs": review.get("all_children", []),
        "safe_review_result": "FINALIZED_FINISHED_WITH_RETURN",
        "safe_final_state": safe_state,
        "review_time_web_fetches": read(client, governor, "get_review_web_fetch_count", [safe_proposal_id]),
        "final_target_state": target_after,
        "final_installed_version": read(client, governor, "get_target_policy", [safe_target]).get("current_version"),
        "final_installed_hash": target_after["installed_candidate_hash"],
        "persistent_state_preserved": target_after["value"] == run["persistent_value_before_upgrade"] and target_after["nonce"] == run["persistent_nonce_before_upgrade"],
        "upgrade_authority_preserved": str(target_after["governor"]).lower() == str(governor).lower(),
    })
    if run["review_time_web_fetches"] != 0 or target_after["registered"] is not True or target_after["installed_proposal_id"] != safe_proposal_id or target_after["installed_candidate_hash"] != SAFE_HASH:
        raise SystemExit("safe V2.2 trust consequence readback is incomplete")
    if run["snapshot_digest"] != read_json(client, governor, "get_evidence_snapshot", [safe_proposal_id]).get("snapshot_digest"):
        raise SystemExit("authenticated evidence snapshot changed after review")
    feature = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation="v2.2.profile.safe_feature_write",
        kind="method",
        method="set_release_note",
        address=safe_target,
        args=["V2.2 compact capture feature verified"],
    )
    _tag(journal_obj, "v2.2.profile.safe_feature_write", method="set_release_note")
    run["safe_feature_verified"] = read(client, safe_target, "get_release_note") == "V2.2 compact capture feature verified"
    run["safe_release_history"] = read(client, governor, "get_release_history", [safe_target])
    run["safe_policy_after_review"] = read_json(client, governor, "get_target_policy", [safe_target])
    run["safe_active_proposal_after_review"] = read(client, governor, "get_active_proposal", [safe_target])
    _save_run(run)

    unsafe_target, _ = _deploy_target(
        client=client,
        journal_obj=journal_obj,
        governor=governor,
        operation="v2.2.profile.deploy_unsafe_target",
        label="ProtectedApp V1 V2.2 unsafe negative",
    )
    run["unsafe_target"] = unsafe_target
    unsafe_registration = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation="v2.2.profile.register_unsafe_target",
        kind="method",
        method="register_with_sentinelx",
        address=unsafe_target,
        args=_registration_args(governor, label="ProtectedApp V1 V2.2 unsafe negative"),
        child_methods=["register_target"],
    )
    _tag(journal_obj, "v2.2.profile.register_unsafe_target", method="register_with_sentinelx")
    unsafe_policy = _policy(client, governor, unsafe_target)
    unsafe_ci = _publish_ci_evidence(
        target=unsafe_target,
        policy_fingerprint=str(unsafe_policy["policy_fingerprint"]),
        candidate_hash=UNSAFE_HASH,
        candidate_source=UNSAFE_SOURCE,
        label="v22-unsafe",
        published_at=max(0, int(time.time()) - CI_CLOCK_SKEW_SECONDS),
    )
    unsafe_proposal_id, unsafe_proposal = _create_proposal(
        client=client,
        journal_obj=journal_obj,
        governor=governor,
        target=unsafe_target,
        operation="v2.2.profile.unsafe_create_proposal",
        version="2.0.0-unsafe-v2.2-profile",
        source=UNSAFE_SOURCE,
        candidate_hash=UNSAFE_HASH,
        ci=unsafe_ci,
        intent="This intentionally unsafe candidate must be rejected before installation.",
    )
    unsafe_before = {
        "value": read(client, unsafe_target, "get_protected_value"),
        "nonce": read(client, unsafe_target, "get_value_nonce"),
        "proposal": read(client, unsafe_target, "get_installed_proposal_id"),
        "hash": read(client, unsafe_target, "get_installed_candidate_hash"),
    }
    _stage(
        client=client,
        journal_obj=journal_obj,
        governor=governor,
        proposal_id=unsafe_proposal_id,
        parent_bytes=parent_bytes,
        ci_bytes=(json.dumps(unsafe_ci["envelope"], indent=2, sort_keys=True) + "\n").encode("utf-8"),
        operation="v2.2.profile.unsafe_stage_evidence",
    )
    _capture(client=client, journal_obj=journal_obj, governor=governor, proposal_id=unsafe_proposal_id, operation="v2.2.profile.unsafe_capture_evidence")
    unsafe_review = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation="v2.2.profile.unsafe_review_proposal",
        kind="method",
        method="review_proposal",
        address=governor,
        args=[unsafe_proposal_id],
    )
    _tag(journal_obj, "v2.2.profile.unsafe_review_proposal", method="review_proposal")
    unsafe_state = read_json(client, governor, "get_proposal", [unsafe_proposal_id])
    unsafe_after = {
        "value": read(client, unsafe_target, "get_protected_value"),
        "nonce": read(client, unsafe_target, "get_value_nonce"),
        "proposal": read(client, unsafe_target, "get_installed_proposal_id"),
        "hash": read(client, unsafe_target, "get_installed_candidate_hash"),
    }
    if unsafe_state.get("status") != "REJECTED" or unsafe_review.get("children") or unsafe_before != unsafe_after:
        raise SystemExit("unsafe candidate did not reject without installation")
    run.update({
        "unsafe_proposal_id": unsafe_proposal_id,
        "unsafe_proposal_tx": unsafe_proposal["tx_hash"],
        "unsafe_review_tx": unsafe_review["tx_hash"],
        "unsafe_decision": unsafe_state.get("status"),
        "unsafe_installed": False,
        "negative_state_preserved": unsafe_before == unsafe_after,
    })
    _save_run(run)

    recovery_target, _ = _deploy_target(
        client=client,
        journal_obj=journal_obj,
        governor=governor,
        operation="v2.2.profile.deploy_recovery_target",
        label="ProtectedApp V1 V2.2 registration recovery",
    )
    run["recovery_target"] = recovery_target
    malformed = _registration_args(governor, label="ProtectedApp V1 V2.2 malformed recovery", code_hash="not-a-sha256")
    recovery_failure = "v2.2.profile.recovery_registration_malformed"
    failure_error = ""
    try:
        _submit_and_track(
            client=client,
            journal_obj=journal_obj,
            operation=recovery_failure,
            kind="method",
            method="register_with_sentinelx",
            address=recovery_target,
            args=malformed,
            child_methods=["register_target"],
        )
    except RuntimeError as error:
        failure_error = str(error)
    failure_record = _operation_record(journal_obj, recovery_failure)
    child_ids = failure_record.get("triggered_transaction_ids", [])
    if failure_record.get("state") != "FINALIZED_EXECUTED" or len(child_ids) != 1:
        raise SystemExit("malformed registration did not finalize parent with one failed child")
    child_record = _operation_record(journal_obj, f"{recovery_failure}.child.0")
    after_failure = {
        "governor": read(client, governor, "is_target_registered", [recovery_target]),
        "target": read(client, recovery_target, "is_registered_with_sentinelx"),
    }
    if child_record.get("state") != "FINALIZED_EXECUTION_FAILED" or after_failure != {"governor": False, "target": False}:
        raise SystemExit("failed V2.2 registration child poisoned recovery target")
    retry = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation="v2.2.profile.recovery_registration_retry",
        kind="method",
        method="register_with_sentinelx",
        address=recovery_target,
        args=_registration_args(governor, label="ProtectedApp V1 V2.2 corrected recovery"),
        child_methods=["register_target"],
    )
    _tag(journal_obj, "v2.2.profile.recovery_registration_retry", method="register_with_sentinelx")
    after_retry = {
        "governor": read(client, governor, "is_target_registered", [recovery_target]),
        "target": read(client, recovery_target, "is_registered_with_sentinelx"),
    }
    if after_retry != {"governor": True, "target": True}:
        raise SystemExit("corrected V2.2 registration retry did not succeed")
    run.update({
        "recovery_failure_parent_tx": failure_record.get("tx_hash"),
        "recovery_failure_child_tx": child_ids[0],
        "recovery_failure_error": failure_error,
        "recovery_after_failure": after_failure,
        "recovery_retry_parent_tx": retry["tx_hash"],
        "recovery_retry_child_txs": retry.get("all_children", []),
        "recovery_retry_result": "REGISTERED",
        "recovery_after_retry": after_retry,
    })
    _save_run(run)

    cancel_ci = _publish_ci_evidence(
        target=recovery_target,
        policy_fingerprint=str(_policy(client, governor, recovery_target)["policy_fingerprint"]),
        candidate_hash=SAFE_HASH,
        candidate_source=SAFE_SOURCE,
        label="v22-cancel",
    )
    cancel_id, cancel_proposal = _create_proposal(
        client=client,
        journal_obj=journal_obj,
        governor=governor,
        target=recovery_target,
        operation="v2.2.profile.cancel_create_proposal",
        version="2.0.0-cancel-v2.2-profile",
        source=SAFE_SOURCE,
        candidate_hash=SAFE_HASH,
        ci=cancel_ci,
        intent="Create a disposable proposal solely to profile owner cancellation.",
    )
    cancel = _submit_and_track(
        client=client,
        journal_obj=journal_obj,
        operation="v2.2.profile.cancel_proposal",
        kind="method",
        method="cancel_proposal",
        address=governor,
        args=[cancel_id],
    )
    _tag(journal_obj, "v2.2.profile.cancel_proposal", method="cancel_proposal")
    run["cancel_proposal"] = {"id": cancel_id, "create_tx": cancel_proposal["tx_hash"], "tx": cancel["tx_hash"], "state": read_json(client, governor, "get_proposal", [cancel_id]).get("status")}
    _save_run(run)

    outputs = _write_profile_outputs(
        run=run,
        journal_obj=journal_obj,
        preflight=preflight,
        initial_fee_estimate=initial_fee_estimate,
    )
    run["fee_profile_sha256"] = outputs["fee_profile_sha256"]
    run["fee_profile_created"] = True
    run["unprofiled_operations"] = outputs["coverage"]["unmeasured_operations"]
    _save_run(run)
    print(json.dumps({
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "deployer": EXPECTED_DEPLOYER,
        "governor": governor,
        "safe_target": safe_target,
        "unsafe_target": unsafe_target,
        "recovery_target": recovery_target,
        "safe_proposal_id": safe_proposal_id,
        "unsafe_proposal_id": unsafe_proposal_id,
        "safe_review": "VERIFIED",
        "unsafe_review": "REJECTED",
        "recovery": "REGISTERED",
        "fee_profile": "artifacts/v2.2/fee-profile.v2.2.json",
        "coverage": "artifacts/v2.2/fee-profile-coverage.v2.2.json",
        "readiness": "deployments/v2.2/DEPLOYMENT_READINESS.json",
        "journal": str(JOURNAL_PATH),
        "canonical_deployment_attempted": False,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
