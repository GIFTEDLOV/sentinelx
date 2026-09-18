"""Perform the first authorized SentinelX Studionet canonical deployment.

This runner is intentionally separate from the disposable qualification
orchestrator.  It uses a fresh journal/state namespace, the locked qualified
source bytes, and the stable genlayer-py bridge.  The contract sources are
read-only inputs to this script.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import types
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SENTINELX_STUDIONET_PROFILE_STATE"] = "studionet-v23-canonical-r1"
os.environ["SENTINELX_STUDIONET_SOURCE_REVISION"] = "cfb25215497adeb41357196caa8c755a685b4cf2"

from scripts import studionet_stable_bridge as bridge  # noqa: E402
from scripts import studionet_v23_source_manifest as source_manifest  # noqa: E402
from scripts import studionet_stable_profile as stable_profile  # noqa: E402


GOVERNOR_SOURCE = ROOT / "contracts" / "sentinelx_governor.py"
TARGET_SOURCE = ROOT / "contracts" / "protected_app_v1.py"
SAFE_SOURCE = ROOT / "contracts" / "protected_app_v2_safe.py"
UNSAFE_SOURCE = ROOT / "contracts" / "protected_app_v2_unsafe.py"
CONSTITUTION = ROOT / "deploy" / "release-constitution.json"
READINESS = ROOT / "deployments" / "studionet" / "v2.3" / "DEPLOYMENT_READINESS.json"
FEE_PROFILE = ROOT / "deployments" / "studionet" / "v2.3" / "fee-profile.json"
SOURCE_MANIFEST = ROOT / "deployments" / "studionet" / "v2.3" / "SOURCE_MANIFEST.json"
LIVE_PROOF = ROOT / "artifacts" / "studionet" / "v2.3" / "canonical-live-proof.json"
CANONICAL_MANIFEST = ROOT / "deployments" / "studionet" / "v2.3" / "CANONICAL_DEPLOYMENT.json"

SOURCE_REVISION = "cfb25215497adeb41357196caa8c755a685b4cf2"
QUALIFICATION_HEAD = "7dca629f7e413deaffad106a6ccad30164ac4ea7"
EXPECTED_SIGNER = bridge.EXPECTED_DEPLOYER
SOURCE_PREFIX = "https://raw.githubusercontent.com/GIFTEDLOV/sentinelx/"
CI_PREFIX = "https://raw.githubusercontent.com/GIFTEDLOV/sentinelx-ci/"
GOVERNOR_HASH = "1c53c221300a5fd4e901a3608c72f87c88ed14136f5a95f786a2854355270423"
PARENT_HASH = "47bf21c12574ec8d43a41d79c987e1206b3c65b3e7f0e7998c8a3ff1179d2631"
SAFE_HASH = "1073b34f141b9dc5ba689ef3d98293fd628e30695dbd9092a9c6ecaba3d8c27d"
UNSAFE_HASH = "380c80e653a2d87e02648eec57dbfd46f898fb1a4cccfbe349c027ffa9149340"
FEE_PROFILE_HASH = "9d50b9cc5fa0e6c66a32eebe9cc68c55f55662009e2f20f22ae6b80138f6776f"
SOURCE_MANIFEST_HASH = "6a4ec43dbc02fe4b1efbf7ed49cca261cb9f4a63a320a379c9b61b10222e529a"
SEMANTIC_VECTOR = (
    "storage_layout_compatible", "public_interface_compatible",
    "user_rights_preserved", "no_privilege_escalation",
    "upgrade_authority_preserved", "consensus_integrity_preserved",
    "finality_safety_preserved", "evidence_trust_preserved", "fund_flow_safe",
    "external_fetch_surface_safe", "liveness_preserved",
    "behavioral_scope_matches_release", "migration_safety_preserved",
    "constitution_satisfied",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    if hasattr(value, "value"):
        return _json(value.value)
    return str(value)


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json(value), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _source_url(relative: str) -> str:
    return f"{SOURCE_PREFIX}{SOURCE_REVISION}/{relative}"


def _current_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _clean_worktree() -> bool:
    return not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()


def _assert_gate() -> dict[str, Any]:
    current_head = _current_head()
    if current_head != QUALIFICATION_HEAD:
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", f"{QUALIFICATION_HEAD}..{current_head}"],
            cwd=ROOT, text=True,
        ).splitlines()
        source_paths = {str(path.relative_to(ROOT)).replace("\\", "/") for path in (
            GOVERNOR_SOURCE, TARGET_SOURCE, SAFE_SOURCE, UNSAFE_SOURCE,
        )}
        if any(path in source_paths for path in changed):
            raise RuntimeError("production contract source changed after qualification")
    if not _clean_worktree():
        raise RuntimeError("worktree is not clean before canonical deployment")
    expected = {
        GOVERNOR_SOURCE: GOVERNOR_HASH, TARGET_SOURCE: PARENT_HASH,
        SAFE_SOURCE: SAFE_HASH, UNSAFE_SOURCE: UNSAFE_HASH,
    }
    actual = {str(path.relative_to(ROOT)): _sha(path) for path in expected}
    if actual != {str(path.relative_to(ROOT)): digest for path, digest in expected.items()}:
        raise RuntimeError(f"qualified source hashes do not match: {actual}")
    if _sha(SOURCE_MANIFEST) != SOURCE_MANIFEST_HASH:
        raise RuntimeError("qualified source manifest hash changed")
    if _sha(FEE_PROFILE) != FEE_PROFILE_HASH:
        raise RuntimeError("qualified fee profile hash changed")
    manifest_errors = source_manifest.verify_manifest(SOURCE_MANIFEST)
    if manifest_errors:
        raise RuntimeError("source manifest validation failed: " + "; ".join(manifest_errors))
    readiness = json.loads(READINESS.read_text(encoding="utf-8"))
    if readiness.get("result") != "PASS" or readiness.get("status") != "PROFILED_NON_CANONICAL":
        raise RuntimeError("qualified readiness manifest is not the expected pre-canonical PASS")
    if readiness.get("canonical_deployment") != "NOT_YET_DEPLOYED":
        raise RuntimeError("canonical deployment was already recorded")
    if readiness.get("source_hashes") != {
        "governor": GOVERNOR_HASH, "target": PARENT_HASH,
        "safe": SAFE_HASH, "unsafe": UNSAFE_HASH,
    }:
        raise RuntimeError("readiness source hashes do not match qualified hashes")
    return {"qualification_head": QUALIFICATION_HEAD, "qualification_head_at_run": current_head, "source_revision": SOURCE_REVISION, "source_hashes": actual}


def _install_legacy_helpers() -> Any:
    """Load only orchestration helpers against the stable bridge."""
    compat = types.ModuleType("scripts.studio_dev_v21_managed_profile")
    compat._verify_cli_source = lambda address, source: bridge.verify_source(_CLIENT, address, source)
    compat._publish_ci_evidence = stable_profile._publish_ci_evidence
    compat._contract_address = bridge._contract_address
    compat.source_sha256 = bridge.source_sha256
    sys.modules["scripts.studio_dev_managed_bridge"] = bridge
    sys.modules["scripts.studio_dev_v21_managed_profile"] = compat
    manifest_alias = types.ModuleType("scripts.v2_source_manifest")
    manifest_alias.verify_manifest = source_manifest.verify_manifest
    sys.modules["scripts.v2_source_manifest"] = manifest_alias
    import scripts.studio_dev_v22_managed_profile as legacy
    legacy.SOURCE_REVISION = SOURCE_REVISION
    legacy.SOURCE_PREFIX = SOURCE_PREFIX
    legacy.CI_PREFIX = CI_PREFIX
    legacy.GOVERNOR_HASH = GOVERNOR_HASH
    legacy.PARENT_HASH = PARENT_HASH
    legacy.SAFE_HASH = SAFE_HASH
    legacy.UNSAFE_HASH = UNSAFE_HASH
    legacy.PROFILE_LABEL = "SENTINELX_STUDIONET_CANONICAL"
    legacy.CONSTITUTION = CONSTITUTION
    return legacy


def _submit(*, journal: Any, operation: str, kind: str, method: str | None = None,
            address: str | None = None, args: list[Any] | None = None,
            source: Path | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    result = bridge.submit(
        client=_CLIENT, journal_obj=journal, operation=operation, kind=kind,
        method=method, address=address, args=args, source=source,
        fee_metadata=metadata,
    )
    children = result.get("children")
    if not isinstance(children, list):
        raise RuntimeError(f"{operation} returned malformed child list")
    result["all_children"] = bridge.track_children(
        client=_CLIENT, journal_obj=journal, parent_operation=operation,
        children=[str(item) for item in children],
    )
    return result


def _registration_args(label: str) -> list[Any]:
    return [
        label,
        CONSTITUTION.read_text(encoding="utf-8"),
        "GIFTEDLOV/sentinelx",
        "GIFTEDLOV/sentinelx-ci",
        "OPTIONAL", "", SOURCE_PREFIX, CI_PREFIX, "",
        "1.0.0-canonical", _source_url("contracts/protected_app_v1.py"),
        PARENT_HASH, 86_400, 3_600, 3_600,
    ]


def _record(run: dict[str, Any], key: str, result: dict[str, Any]) -> None:
    run[key] = {
        "tx_hash": result.get("tx_hash"),
        "children": result.get("children", []),
        "all_children": result.get("all_children", []),
    }
    _write(_RUN_PATH, run)


def _proposal(client: Any, governor: str, proposal_id: int) -> dict[str, Any]:
    value = bridge.read_json(client, governor, "get_proposal", [proposal_id])
    return value


def _assert_address(value: Any, expected: str, label: str) -> None:
    if str(value).lower().replace("addr#", "") != expected.lower():
        raise RuntimeError(f"{label} mismatch: {value} != {expected}")


def main() -> int:
    global _CLIENT, _RUN_PATH
    gate = _assert_gate()
    _CLIENT = bridge.make_client()
    journal = bridge.journal()
    _RUN_PATH = bridge.LOCAL_STATE / "run.json"
    preflight = bridge.account_preflight(_CLIENT, EXPECTED_SIGNER, journal)
    if int(preflight["chain_id"]) != 61999 or preflight["rpc"] != bridge.RPC:
        raise RuntimeError("stable network preflight failed")
    if int(preflight["latest_nonce"]) != int(preflight["pending_nonce"]):
        raise RuntimeError("latest and pending nonce differ before canonical writes")
    if preflight["unresolved_journal_operations"]:
        raise RuntimeError("canonical journal has unresolved operations")
    run: dict[str, Any] = {
        "schema": "sentinelx-studionet-v23-canonical-run-v1",
        "network": bridge.NETWORK, "rpc": bridge.RPC, "chain_id": bridge.CHAIN_ID,
        "source_revision": SOURCE_REVISION, "qualification_head": QUALIFICATION_HEAD,
        "canonical_deployment_artifact_head": _current_head(),
        "signer": EXPECTED_SIGNER, "balance_before": preflight["balance_wei"],
        "nonce_before": preflight["latest_nonce"],
        "fee_profile_sha256": _sha(FEE_PROFILE),
        "fee_policy_before": _json(preflight["fee_policy"]),
        "canonical_deployment_attempted": True,
    }
    if _RUN_PATH.exists():
        old = json.loads(_RUN_PATH.read_text(encoding="utf-8"))
        if not isinstance(old, dict) or old.get("source_revision") != SOURCE_REVISION:
            raise RuntimeError("canonical run state belongs to another source revision")
        run.update(old)
    _write(_RUN_PATH, run)

    legacy = _install_legacy_helpers()

    # Governor deployment.
    governor_op = "canonical.deploy_governor"
    governor_result = _submit(
        journal=journal, operation=governor_op, kind="deploy", source=GOVERNOR_SOURCE,
        metadata={"contract_name": "sentinelx_governor", "deployment_label": "SENTINELX_STUDIONET_CANONICAL"},
    )
    governor = bridge._contract_address(governor_result["receipt"])
    if not governor:
        governor = run.get("governor")
    if not governor:
        raise RuntimeError("canonical governor address missing")
    run["governor"] = governor
    _record(run, "governor_deployment", governor_result)
    run["governor_contract_info"] = bridge.read(_CLIENT, governor, "contract_info")
    run["governor_source_parity"] = bridge.verify_source(_CLIENT, governor, GOVERNOR_SOURCE)
    _write(_RUN_PATH, run)

    # Fresh baseline target deployment.
    target_result = _submit(
        journal=journal, operation="canonical.deploy_target", kind="deploy", source=TARGET_SOURCE,
        args=[governor, "SentinelX canonical protected target", "SentinelX canonical initial"],
        metadata={"contract_name": "protected_app_v1", "deployment_label": "SENTINELX_STUDIONET_CANONICAL"},
    )
    target = bridge._contract_address(target_result["receipt"]) or run.get("target")
    if not target:
        raise RuntimeError("canonical target address missing")
    run["target"] = target
    _record(run, "target_deployment", target_result)
    run["target_source_parity"] = bridge.verify_source(_CLIENT, target, TARGET_SOURCE)
    before = {
        "owner": bridge.read(_CLIENT, target, "get_owner"),
        "governor": bridge.read(_CLIENT, target, "get_upgrade_governor"),
        "application_name": bridge.read(_CLIENT, target, "get_application_name"),
        "value": bridge.read(_CLIENT, target, "get_protected_value"),
        "nonce": bridge.read(_CLIENT, target, "get_value_nonce"),
        "installed_proposal_id": bridge.read(_CLIENT, target, "get_installed_proposal_id"),
        "installed_candidate_hash": bridge.read(_CLIENT, target, "get_installed_candidate_hash"),
        "registered": bridge.read(_CLIENT, target, "is_registered_with_sentinelx"),
    }
    _assert_address(before["owner"], EXPECTED_SIGNER, "canonical target owner")
    _assert_address(before["governor"], governor, "canonical target governor")
    if before["installed_proposal_id"] != 0 or before["installed_candidate_hash"] != "" or before["registered"] is not False:
        raise RuntimeError("canonical target is not fresh baseline state")
    run["target_before"] = before
    _write(_RUN_PATH, run)

    persistent_value = "SentinelX canonical persistent state before upgrade"
    persistent = _submit(
        journal=journal, operation="canonical.set_persistent_value", kind="method",
        method="set_protected_value", address=target, args=[persistent_value],
    )
    _record(run, "persistent_write", persistent)
    run["persistent_value_before_upgrade"] = bridge.read(_CLIENT, target, "get_protected_value")
    run["persistent_nonce_before_upgrade"] = bridge.read(_CLIENT, target, "get_value_nonce")
    _write(_RUN_PATH, run)

    # Target-originated OPTIONAL registration and finalized child.
    registration = _submit(
        journal=journal, operation="canonical.register_target", kind="method",
        method="register_with_sentinelx", address=target, args=_registration_args("SentinelX canonical protected target"),
    )
    _record(run, "registration", registration)
    policy = bridge.read_json(_CLIENT, governor, "get_target_policy", [target])
    if bridge.read(_CLIENT, governor, "is_target_registered", [target]) is not True:
        raise RuntimeError("canonical governor registration readback failed")
    if bridge.read(_CLIENT, target, "is_registered_with_sentinelx") is not True:
        raise RuntimeError("canonical target registration readback failed")
    if policy.get("security_attestation_mode") != "OPTIONAL" or not policy.get("active") or not policy.get("policy_fingerprint"):
        raise RuntimeError("canonical OPTIONAL policy readback failed")
    if policy.get("current_code_hash") != PARENT_HASH:
        raise RuntimeError("canonical policy parent hash mismatch")
    _assert_address(policy.get("target"), target, "canonical policy target")
    run["policy"] = policy
    run["policy_fingerprint"] = policy["policy_fingerprint"]
    _write(_RUN_PATH, run)

    # Fresh immutable CI evidence; the helper fetch-verifies exact bytes.
    ci = stable_profile._publish_ci_evidence(
        target=target, policy_fingerprint=str(policy["policy_fingerprint"]),
        candidate_hash=SAFE_HASH, candidate_source=SAFE_SOURCE,
        label=f"canonical-safe-{target.lower()}", published_at=max(0, int(time.time()) - 300),
    )
    run["ci"] = ci
    _write(_RUN_PATH, run)
    ci_bytes = (json.dumps(ci["envelope"], indent=2, sort_keys=True) + "\n").encode("utf-8")

    # Exact candidate proposal.
    proposal_result = _submit(
        journal=journal, operation="canonical.create_safe_proposal", kind="method",
        method="create_proposal", address=governor,
        args=[target, "2.0.0-safe-v2.3-canonical", _source_url("contracts/protected_app_v2_safe.py"),
              SAFE_SOURCE.read_bytes(), str(ci["url"]), str(ci["evidence_id"]), "", "",
              "Add the verified release status feature without changing owner rights or upgrade authority."],
    )
    _record(run, "proposal_creation", proposal_result)
    proposal_id = int(bridge.read(_CLIENT, governor, "get_active_proposal", [target]))
    if proposal_id <= 0:
        raise RuntimeError("canonical proposal ID is not positive")
    proposal_state = _proposal(_CLIENT, governor, proposal_id)
    if proposal_state.get("candidate_code_hash") != SAFE_HASH or proposal_state.get("parent_code_hash") != PARENT_HASH or proposal_state.get("policy_fingerprint") != policy["policy_fingerprint"]:
        raise RuntimeError("canonical proposal binding mismatch")
    run["proposal_id"] = proposal_id
    run["proposal"] = proposal_state
    _write(_RUN_PATH, run)

    stage = _submit(
        journal=journal, operation="canonical.stage_evidence", kind="method",
        method="stage_evidence", address=governor,
        args=[proposal_id, TARGET_SOURCE.read_bytes(), ci_bytes, b""],
    )
    _record(run, "stage", stage)
    staged = bridge.read_json(_CLIENT, governor, "get_staged_evidence", [proposal_id])
    staged_proposal = _proposal(_CLIENT, governor, proposal_id)
    if staged_proposal.get("status") != "EVIDENCE_STAGED" or staged_proposal.get("evidence_ready") is True:
        raise RuntimeError("canonical stage did not leave EVIDENCE_STAGED / not-ready state")
    run["staged"] = staged
    run["staged_digest"] = staged.get("staged_digest")
    run["ready_after_stage"] = False
    _write(_RUN_PATH, run)

    capture = _submit(
        journal=journal, operation="canonical.capture_evidence", kind="method",
        method="capture_evidence", address=governor, args=[proposal_id],
    )
    _record(run, "capture", capture)
    capture_record = journal.load()["operations"]["canonical.capture_evidence"]
    capture_serialized = json.dumps(capture_record, sort_keys=True).encode("utf-8")
    if len(capture_serialized) > 4_096 or "bytes_hex" in capture_serialized.decode("utf-8", errors="ignore"):
        raise RuntimeError("canonical compact capture result is not bounded/compact")
    snapshot = bridge.read_json(_CLIENT, governor, "get_evidence_snapshot", [proposal_id])
    if snapshot.get("status") != "EVIDENCE_READY" or snapshot.get("security_present") is not False:
        raise RuntimeError("canonical capture did not authenticate OPTIONAL snapshot")
    run["compact_result_size"] = len(capture_serialized)
    run["snapshot_digest"] = snapshot.get("snapshot_digest")
    run["ready_after_capture"] = True
    run["snapshot"] = snapshot
    _write(_RUN_PATH, run)

    review = _submit(
        journal=journal, operation="canonical.review", kind="method",
        method="review_proposal", address=governor, args=[proposal_id],
    )
    _record(run, "review", review)
    reviewed = _proposal(_CLIENT, governor, proposal_id)
    vector = reviewed.get("semantic_vector")
    fetches = bridge.read(_CLIENT, governor, "get_review_web_fetch_count", [proposal_id])
    if reviewed.get("status") != "UPGRADE_QUEUED" or reviewed.get("last_review_code") not in ("APPROVED", "APPROVE"):
        raise RuntimeError(f"canonical review did not queue APPROVE: {reviewed}")
    if fetches != 0 or not isinstance(vector, dict) or tuple(vector.keys()) != tuple(vector.keys()) or set(vector) != set(SEMANTIC_VECTOR) or any(value is not True for value in vector.values()):
        raise RuntimeError("canonical review did not produce exact zero-fetch 14/14 vector")
    run["reviewed"] = reviewed
    run["review_time_web_fetches"] = fetches
    run["semantic_vector"] = vector
    _write(_RUN_PATH, run)

    # Execute once.  If only the confirmation grandchild fails after an exact
    # finalized install, use the qualified owner-only target retry once.
    execute: dict[str, Any]
    execute_error = ""
    try:
        execute = _submit(
            journal=journal, operation="canonical.execute_upgrade", kind="method",
            method="execute_reviewed_upgrade", address=governor, args=[proposal_id],
        )
    except RuntimeError as error:
        execute_error = str(error)
        record = journal.load()["operations"].get("canonical.execute_upgrade", {})
        if record.get("state") != "FINALIZED_EXECUTED" or record.get("lifecycle_status") != "FINALIZED":
            raise
        direct_children = record.get("triggered_transaction_ids", [])
        execute = {"tx_hash": record.get("tx_hash"), "children": direct_children, "all_children": direct_children, "recovered_after_child_error": True}
    _record(run, "execute", execute)
    run["execute_error"] = execute_error
    target_installed_id = bridge.read(_CLIENT, target, "get_installed_proposal_id")
    target_installed_hash = bridge.read(_CLIENT, target, "get_installed_candidate_hash")
    if target_installed_id != proposal_id or target_installed_hash != SAFE_HASH:
        raise RuntimeError("canonical target did not install exact safe candidate")
    run["install_child_tx"] = execute.get("children", [None])[0] if execute.get("children") else None
    all_children = execute.get("all_children", [])
    run["confirmation_child_tx"] = all_children[1] if len(all_children) > 1 else None
    _write(_RUN_PATH, run)

    proposal_after_install = _proposal(_CLIENT, governor, proposal_id)
    recovery: dict[str, Any] | None = None
    if proposal_after_install.get("status") != "VERIFIED":
        # Only the target's own authenticated local state authorizes this
        # recovery transaction.  No governor-side cross-contract claim is used.
        recovery = _submit(
            journal=journal, operation="canonical.retry_install_confirmation", kind="method",
            method="retry_install_confirmation", address=target, args=[proposal_id],
        )
        _record(run, "recovery", recovery)
    run["recovery_tx"] = recovery.get("tx_hash") if recovery else None

    final_proposal = _proposal(_CLIENT, governor, proposal_id)
    final_policy = bridge.read_json(_CLIENT, governor, "get_target_policy", [target])
    release_history = bridge.read(_CLIENT, governor, "get_release_history", [target])
    active = bridge.read(_CLIENT, governor, "get_active_proposal", [target])
    final_target = {
        "installed_proposal_id": bridge.read(_CLIENT, target, "get_installed_proposal_id"),
        "installed_candidate_hash": bridge.read(_CLIENT, target, "get_installed_candidate_hash"),
        "protected_value": bridge.read(_CLIENT, target, "get_protected_value"),
        "value_nonce": bridge.read(_CLIENT, target, "get_value_nonce"),
        "upgrade_governor": bridge.read(_CLIENT, target, "get_upgrade_governor"),
    }
    if final_proposal.get("status") != "VERIFIED" or active not in (0, "0"):
        raise RuntimeError(f"canonical release did not reach VERIFIED with no active proposal: {final_proposal}")
    if final_target["installed_proposal_id"] != proposal_id or final_target["installed_candidate_hash"] != SAFE_HASH:
        raise RuntimeError("canonical final target hash/proposal mismatch")
    if final_policy.get("current_code_hash") != SAFE_HASH or final_policy.get("current_version") != "2.0.0-safe-v2.3-canonical":
        raise RuntimeError("canonical governor policy did not advance to safe release")
    if final_target["protected_value"] != persistent_value or final_target["value_nonce"] != 1:
        raise RuntimeError("canonical persistent state was not preserved")
    _assert_address(final_target["upgrade_governor"], governor, "canonical upgrade governor")

    feature_text = "SentinelX canonical V2.3 safe feature verified"
    feature = _submit(
        journal=journal, operation="canonical.safe_feature", kind="method",
        method="set_release_note", address=target, args=[feature_text],
    )
    _record(run, "safe_feature", feature)
    safe_feature_verified = bridge.read(_CLIENT, target, "get_release_note") == feature_text

    run.update({
        "proposal_id": proposal_id, "final_proposal": final_proposal,
        "final_policy": final_policy, "release_history": release_history,
        "active_proposal": active, "final_target": final_target,
        "persistent_state_preserved": final_target["protected_value"] == persistent_value and final_target["value_nonce"] == 1,
        "value_nonce_preserved": final_target["value_nonce"] == 1,
        "upgrade_authority_preserved": True, "safe_feature_verified": safe_feature_verified,
        "release_history_verified": str(proposal_id) in json.dumps(release_history),
        "canonical_result": "PASS" if safe_feature_verified else "FAIL",
    })
    _write(_RUN_PATH, run)
    if not safe_feature_verified:
        raise RuntimeError("canonical safe feature readback failed")

    proof = {
        "schema": "sentinelx-studionet-v23-canonical-live-proof-v1",
        "phase": "CANONICAL_STUDIONET_RELEASE",
        "network": bridge.NETWORK, "rpc": bridge.RPC, "chain_id": bridge.CHAIN_ID,
        "source_revision": SOURCE_REVISION, "qualification_head": QUALIFICATION_HEAD,
        "canonical_deployment_artifact_head": run["canonical_deployment_artifact_head"],
        "signer": EXPECTED_SIGNER, "balance_before": preflight["balance_wei"],
        "governor": governor, "target": target,
        "governor_deploy_tx": run["governor_deployment"]["tx_hash"],
        "target_deploy_tx": run["target_deployment"]["tx_hash"],
        "registration_parent_tx": run["registration"]["tx_hash"],
        "registration_children": run["registration"].get("all_children", []),
        "policy_fingerprint": run["policy_fingerprint"],
        "ci": {k: ci.get(k) for k in ("commit", "url", "evidence_id", "sha256", "fetched_verified")},
        "proposal_id": proposal_id, "proposal_tx": run["proposal_creation"]["tx_hash"],
        "stage_tx": run["stage"]["tx_hash"], "staged_digest": run["staged_digest"],
        "capture_tx": run["capture"]["tx_hash"], "snapshot_digest": run["snapshot_digest"],
        "compact_result_size": run["compact_result_size"],
        "review_tx": run["review"]["tx_hash"], "review_web_fetches": fetches,
        "semantic_vector": vector, "decision": "APPROVE",
        "execute_tx": run["execute"]["tx_hash"], "install_child_tx": run["install_child_tx"],
        "confirmation_child_tx": run["confirmation_child_tx"], "recovery_tx": run["recovery_tx"],
        "final_proposal_state": final_proposal.get("status"), "final_review_code": final_proposal.get("last_review_code"),
        "installed_hash": final_target["installed_candidate_hash"],
        "persistent_state_preserved": run["persistent_state_preserved"],
        "value_nonce_preserved": run["value_nonce_preserved"],
        "upgrade_authority_preserved": run["upgrade_authority_preserved"],
        "safe_feature_verified": safe_feature_verified,
        "qualified_unsafe_profile": {"decision": "REJECTED", "installed": False, "source_hash": UNSAFE_HASH},
        "fee_profile_sha256": FEE_PROFILE_HASH, "source_manifest_sha256": SOURCE_MANIFEST_HASH,
        "source_hashes": {"governor": GOVERNOR_HASH, "target": PARENT_HASH, "safe": SAFE_HASH, "unsafe": UNSAFE_HASH},
        "toolchain": source_manifest.build_manifest(source_commit=SOURCE_REVISION)["toolchain"],
        "canonical_deployment_attempted": True,
        "result": "PASS",
    }
    _write(LIVE_PROOF, proof)
    _write(CANONICAL_MANIFEST, {
        "schema": "sentinelx-studionet-v23-canonical-deployment-v1",
        "network": "Studionet", "rpc": bridge.RPC, "chain_id": bridge.CHAIN_ID,
        "source_revision": SOURCE_REVISION, "qualification_head": QUALIFICATION_HEAD,
        "canonical_deployment_artifact_head": run["canonical_deployment_artifact_head"],
        "canonical_governor": governor, "canonical_target": target,
        "governor_deploy_tx": proof["governor_deploy_tx"], "target_deploy_tx": proof["target_deploy_tx"],
        "registration_parent_tx": proof["registration_parent_tx"], "registration_child_txs": proof["registration_children"],
        "policy_fingerprint": proof["policy_fingerprint"], "canonical_ci": proof["ci"],
        "proposal_id": proposal_id, "proposal_tx": proof["proposal_tx"],
        "stage_tx": proof["stage_tx"], "stage_digest": proof["staged_digest"],
        "capture_tx": proof["capture_tx"], "snapshot_digest": proof["snapshot_digest"],
        "compact_output_size": proof["compact_result_size"],
        "review_tx": proof["review_tx"], "review_web_fetch_count": proof["review_web_fetches"],
        "semantic_vector": proof["semantic_vector"], "decision": "APPROVE",
        "execute_tx": proof["execute_tx"], "install_child_tx": proof["install_child_tx"],
        "confirmation_child_tx": proof["confirmation_child_tx"], "recovery_tx": proof["recovery_tx"],
        "final_proposal_state": proof["final_proposal_state"], "installed_safe_sha256": SAFE_HASH,
        "persistent_state_proof": run["persistent_state_preserved"],
        "authority_proof": run["upgrade_authority_preserved"], "safe_feature_proof": safe_feature_verified,
        "qualified_unsafe_profile_reference": proof["qualified_unsafe_profile"],
        "fee_profile_sha256": FEE_PROFILE_HASH, "source_manifest_sha256": SOURCE_MANIFEST_HASH,
        "source_hashes": proof["source_hashes"], "toolchain": proof["toolchain"],
        "canonical_deployment_timestamp": int(time.time()),
        "canonical_deployment_attempted": True, "result": "PASS",
    })
    print(json.dumps({"result": "PASS", "governor": governor, "target": target, "proposal_id": proposal_id, "proof": str(LIVE_PROOF), "manifest": str(CANONICAL_MANIFEST), "journal": str(bridge.JOURNAL_PATH)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
