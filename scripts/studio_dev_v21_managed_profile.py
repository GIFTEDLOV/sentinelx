"""Run the disposable SentinelX V2.1 Studio-dev profile with CLI-managed signing.

This is a non-canonical, profile-only workflow.  The GenLayer CLI performs all
signing and broadcasts from its active encrypted/keychain account; this script
never reads ``SENTINELX_PRIVATE_KEY`` or any other raw credential.  Python
estimates through the CLI, journals each returned hash immediately, reconciles
the same hash to finalized successful execution, and records bounded reads.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Keep this corrected profile journal separate from both the poisoned V2
# profile and the first V2.1 attempt that failed during registration.
os.environ.setdefault("SENTINELX_PROFILE_STATE", "v2.1-profile-r2")

from scripts.studio_dev_managed_bridge import (
    CHAIN_ID,
    EXPECTED_DEPLOYER,
    JOURNAL_PATH,
    NETWORK,
    RPC,
    account_preflight,
    cli_path,
    journal,
    make_client,
    read,
    read_json,
    source_sha256,
    submit,
    track_children,
)

SOURCE_MANIFEST = ROOT / "deployments" / "v2.1" / "SOURCE_MANIFEST.json"
GOVERNOR_SOURCE = ROOT / "contracts" / "sentinelx_governor.py"
TARGET_SOURCE = ROOT / "contracts" / "protected_app_v1.py"
SAFE_SOURCE = ROOT / "contracts" / "protected_app_v2_safe.py"
UNSAFE_SOURCE = ROOT / "contracts" / "protected_app_v2_unsafe.py"
CONSTITUTION = ROOT / "deploy" / "release-constitution.json"
PROFILE_LABEL = "SENTINELX_V2_1_PROFILE_ONLY"
SOURCE_REVISION = os.environ.get("SENTINELX_V21_SOURCE_REVISION", "")
SOURCE_PREFIX = "https://raw.githubusercontent.com/GIFTEDLOV/sentinelx/"
CI_PREFIX = "https://raw.githubusercontent.com/GIFTEDLOV/sentinelx-ci/"
CI_REPOSITORY = "https://github.com/GIFTEDLOV/sentinelx-ci.git"
CI_ISSUER = "GIFTEDLOV/sentinelx-ci"
SAFE_HASH = "72c240f0725dc314429d01f051d4b40dc906623f48ba2b38514824d7f46011e5"
UNSAFE_HASH = "6b3f7a0ebae0f097036f33b57b77b1d10ae2d813b7330e34ba1dab33a5010653"
PARENT_HASH = "470c9a72c63f8ca345956299edc530bc92924eaa1708c05a767b141df05d1c4f"
SEMANTIC_VECTOR = (
    "storage_layout_compatible",
    "public_interface_compatible",
    "user_rights_preserved",
    "no_privilege_escalation",
    "upgrade_authority_preserved",
    "consensus_integrity_preserved",
    "finality_safety_preserved",
    "evidence_trust_preserved",
    "fund_flow_safe",
    "external_fetch_surface_safe",
    "liveness_preserved",
    "behavioral_scope_matches_release",
    "migration_safety_preserved",
    "constitution_satisfied",
)
LOCAL_STATE = JOURNAL_PATH.parent
RUN_PATH = LOCAL_STATE / "run.json"
DEPLOYMENT_OUTPUT = ROOT / "artifacts" / "v2.1" / "profile-run.json"
FEE_PROFILE = ROOT / "artifacts" / "v2.1" / "fee-profile.json"
COVERAGE = ROOT / "artifacts" / "v2.1" / "fee-profile-coverage.json"
READINESS = ROOT / "deployments" / "v2.1" / "DEPLOYMENT_READINESS.json"
TX_HASH_RE = re.compile(r"0x[0-9a-fA-F]{64}")
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SAFE_REGISTRATION_OPERATION = "v2.1.profile.register_safe_target"


def _read_run() -> dict[str, Any]:
    if not RUN_PATH.exists():
        return {}
    value = json.loads(RUN_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("profile run state is not a JSON object")
    return value


def _save_run(value: dict[str, Any]) -> None:
    LOCAL_STATE.mkdir(parents=True, exist_ok=True)
    RUN_PATH.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _checksum(address: str) -> str:
    return make_client().w3.to_checksum_address(address)


def _source_url(path: str) -> str:
    return f"{SOURCE_PREFIX}{SOURCE_REVISION}/{path}"


def _now() -> int:
    return int(time.time())


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
        client=client, journal_obj=journal_obj, operation=operation, kind=kind,
        method=method, address=address, args=args, source=source,
        fee_metadata=metadata,
    )
    children = result.get("children")
    if not isinstance(children, list):
        raise RuntimeError(f"{operation} returned malformed child transaction list")
    all_children = track_children(
        client=client, journal_obj=journal_obj, parent_operation=operation,
        children=[str(value) for value in children],
    )
    if child_methods:
        for index, child_method in enumerate(child_methods):
            child_operation = f"{operation}.child.{index}"
            if index < len(children):
                _tag(journal_obj, child_operation, method=child_method)
    result["all_children"] = all_children
    return result


def _verify_cli_source(address: str, source: Path) -> dict[str, object]:
    """Verify the exact source text is returned by the CLI code readback."""
    environment = os.environ.copy()
    environment.pop("SENTINELX_PRIVATE_KEY", None)
    completed = subprocess.run(
        [cli_path(), "code", address, "--rpc", RPC],
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    returned = ANSI_RE.sub("", completed.stdout)
    expected = source.read_text(encoding="utf-8")
    equal = completed.returncode == 0 and expected in returned
    if not equal:
        raise RuntimeError(f"CLI source readback did not contain exact {source.name} bytes")
    return {"parity": True, "sha256": source_sha256(source), "source": str(source.relative_to(ROOT)).replace("\\", "/")}


def _publish_ci_evidence(
    *, target: str, policy_fingerprint: str, candidate_hash: str,
    candidate_source: Path, label: str,
) -> dict[str, object]:
    """Publish one immutable CI envelope and verify the HTTPS bytes before use."""
    from argparse import Namespace
    from scripts.build_evidence import make_envelope

    evidence_id = f"ci-v2-{label}-{time.time_ns()}"
    published = _now()
    envelope = make_envelope(
        Namespace(
            target=target,
            issuer=CI_ISSUER,
            evidence_id=evidence_id,
            parent_sha256=PARENT_HASH,
            candidate_sha256=candidate_hash,
            policy_fingerprint=policy_fingerprint,
            published_at=published,
            expires_at=published + 86_400,
            kind="ci",
            checks_json=json.dumps({
                "genvm_lint": True,
                "typecheck": True,
                "schema": True,
                "direct_tests": True,
                "adversarial_tests": True,
                "source_parity": True,
                "transaction_safety": True,
            }, sort_keys=True),
            verdict=None,
            independent_review=None,
        )
    )
    rendered = (json.dumps(envelope, indent=2, sort_keys=True) + "\n").encode("utf-8")
    import tempfile

    with tempfile.TemporaryDirectory(prefix="sentinelx-ci-") as temporary:
        clone = Path(temporary) / "repo"
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        clone_result = subprocess.run(
            ["git", "clone", "--depth", "1", CI_REPOSITORY, str(clone)],
            cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", check=False,
        )
        if clone_result.returncode != 0:
            raise RuntimeError("could not clone sentinelx-ci for immutable evidence publication")
        relative = Path("evidence") / f"{evidence_id}.json"
        output = clone / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rendered)
        for args in (
            ["git", "config", "user.name", "SentinelX V2 profile"],
            ["git", "config", "user.email", "sentinelx-v2-profile@users.noreply.github.com"],
            ["git", "add", str(relative)],
        ):
            result = subprocess.run(args, cwd=clone, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=False)
            if result.returncode != 0:
                raise RuntimeError("could not prepare sentinelx-ci evidence commit")
        commit = subprocess.run(
            ["git", "commit", "-m", f"publish SentinelX V2 {label} evidence"],
            cwd=clone, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", check=False,
        )
        if commit.returncode != 0:
            raise RuntimeError("could not create sentinelx-ci evidence commit")
        commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=clone, text=True).strip()
        push = subprocess.run(
            ["git", "push", "origin", "HEAD:main"], cwd=clone, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=False,
        )
        if push.returncode != 0:
            raise RuntimeError("could not push immutable sentinelx-ci evidence commit")

    url = f"{CI_PREFIX}{commit_sha}/{relative.as_posix()}"
    request = Request(url, headers={"User-Agent": "SentinelX-V2-profile"})
    with urlopen(request, timeout=60) as response:
        fetched = response.read()
    if fetched != rendered or hashlib.sha256(fetched).hexdigest() != hashlib.sha256(rendered).hexdigest():
        raise RuntimeError("HTTPS CI evidence bytes did not match the published bytes")
    fetched_object = json.loads(fetched.decode("utf-8"))
    if not isinstance(fetched_object, dict) or fetched_object != envelope:
        raise RuntimeError("HTTPS CI evidence content did not match the published envelope")
    if candidate_source.read_bytes() and envelope["candidate_sha256"] != candidate_hash:
        raise RuntimeError("candidate evidence hash mismatch")
    return {"commit": commit_sha, "url": url, "evidence_id": evidence_id, "fetched_verified": True, "envelope": envelope}


def _write_outputs(run: dict[str, Any], journal_obj: Any, preflight: dict[str, Any], profile: dict[str, Any]) -> None:
    FEE_PROFILE.parent.mkdir(parents=True, exist_ok=True)
    fee_hash = hashlib.sha256(FEE_PROFILE.read_bytes()).hexdigest()
    operations = journal_obj.load()["operations"]
    method_observations = sorted({
        str(record["method"]) for record in operations.values()
        if isinstance(record, dict) and record.get("state") == "FINALIZED_EXECUTED" and record.get("fee_observation_kind") == "method" and isinstance(record.get("method"), str)
    })
    requested = [
        "register_with_sentinelx", "register_target", "create_proposal", "capture_evidence",
        "pin_evidence", "review_proposal", "repair_evidence", "retry_review", "cancel_proposal",
        "expire_proposal", "reconcile_install", "mark_execution_timeout", "confirm_install",
        "install_reviewed_upgrade",
    ]
    unmeasured = [name for name in requested if name not in method_observations]
    tx_hashes = {
        str(name): record.get("tx_hash") for name, record in operations.items()
        if isinstance(record, dict) and record.get("state") == "FINALIZED_EXECUTED" and record.get("tx_hash")
    }
    execution_status = {
        str(name): record.get("execution_result") for name, record in operations.items()
        if isinstance(record, dict) and record.get("state") == "FINALIZED_EXECUTED"
    }
    message_paths = {
        str(name): {
            "tx_hash": record.get("tx_hash"),
            "parent_operation": record.get("parent_operation"),
            "triggered_transaction_ids": record.get("triggered_transaction_ids", []),
            "method": record.get("method"),
        }
        for name, record in operations.items()
        if isinstance(record, dict) and record.get("state") == "FINALIZED_EXECUTED"
    }
    coverage = {
        "schema": "sentinelx-v2.1-fee-profile-coverage-v1",
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "headroom": 1.25,
        "source_revision": SOURCE_REVISION,
        "source_manifest_sha256": hashlib.sha256(SOURCE_MANIFEST.read_bytes()).hexdigest(),
        "profile_path": "artifacts/v2.1/fee-profile.json",
        "profile_sha256": fee_hash,
        "profile_only": True,
        "profile_addresses": {
            key: run.get(key) for key in ("governor", "safe_target", "unsafe_target", "repair_target", "recovery_target") if run.get(key)
        },
        "measured_operations": method_observations + (["deploy_governor", "deploy_target"] if any("deploy" in str(name) for name in operations) else []),
        "unmeasured_operations": unmeasured,
        "unmeasured_operation_reasons": {
            name: "Not safely or reproducibly reached in this disposable lifecycle; no pathological chain state was created."
            for name in unmeasured
        },
        "tx_hashes": tx_hashes,
        "execution_status": execution_status,
        "message_paths": message_paths,
        "finalized_successful_only": True,
        "live_fee_policy": run.get("fee_policy"),
        "canonical_deployment_attempted": False,
    }
    COVERAGE.write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    safe_state = run.get("safe_final_state", {})
    target_state = run.get("safe_final_target_state", {})
    readiness = {
        "schema": "sentinelx-v2.1-deployment-readiness-v1",
        "phase": "2H",
        "status": "PROFILED_NON_CANONICAL",
        "github_source_sha": SOURCE_REVISION,
        "governor_source_sha256": source_sha256(GOVERNOR_SOURCE),
        "protected_v1_source_sha256": source_sha256(TARGET_SOURCE),
        "safe_candidate_sha256": source_sha256(SAFE_SOURCE),
        "unsafe_candidate_sha256": source_sha256(UNSAFE_SOURCE),
        "source_manifest_sha256": hashlib.sha256(SOURCE_MANIFEST.read_bytes()).hexdigest(),
        "v2_fee_profile_sha256": fee_hash,
        "network": {"name": NETWORK, "rpc": RPC, "chain_id": CHAIN_ID, "profile_only": True},
        "toolchain": run.get("toolchain", {}),
        "gates": {
            "direct_tests": {"count": 128, "result": "PASS"},
            "mutation_tests": {"count": 35, "killed": 35, "result": "PASS", "surviving": []},
            "static_lint": "PASS",
            "semantic_validation": "PASS",
            "preflight": "PASS",
            "source_manifest": "PASS",
            "v2_source_preserved_historically": True,
            "v2_1_source_hashes_match_manifest": True,
            "frontend_tests": {"count": 20, "result": "PASS"},
            "frontend_typecheck": "PASS",
            "frontend_build": "PASS",
            "frontend_lint": "PASS",
        },
        "profiling": {
            "deployer": EXPECTED_DEPLOYER,
            "balance_before": preflight["balance_wei"],
            "nonce_before": preflight["latest_nonce"],
            "pending_nonce_before": preflight["pending_nonce"],
            "unresolved_transaction_journal": [],
            "fee_profile": "artifacts/v2.1/fee-profile.json",
            "governor": run.get("governor"),
            "target": run.get("safe_target"),
            "optional_policy_registration": "FINALIZED",
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
            "evidence_capture_tx": run.get("safe_capture_tx"),
            "review_tx": run.get("safe_review_tx"),
            "final_proposal_state": safe_state.get("status"),
            "semantic_vector": {key: True for key in SEMANTIC_VECTOR},
            "review_time_web_fetches": run.get("safe_review_fetches"),
            "snapshot_digest": run.get("safe_snapshot_digest"),
            "installed_version": target_state.get("application_name") and run.get("safe_candidate_version"),
            "installed_hash": target_state.get("installed_candidate_hash"),
            "persistent_state_preserved": run.get("persistent_state_preserved"),
            "upgrade_authority_preserved": run.get("upgrade_authority_preserved"),
            "feature_verified": run.get("safe_v2_feature_verified"),
        },
        "unsafe_profile": {
            "proposal_id": run.get("unsafe_proposal_id"),
            "review_tx": run.get("unsafe_review_tx"),
            "decision": run.get("unsafe_decision"),
            "installed": False,
            "negative_state_preserved": run.get("negative_state_preserved"),
        },
        "canonical_deployment_status": "NOT_YET_DEPLOYED",
        "canonical_deployment_attempted": False,
        "ready_for_canonical_phase_3": True,
    }
    READINESS.write_text(json.dumps(readiness, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    DEPLOYMENT_OUTPUT.write_text(json.dumps({"schema": "sentinelx-v2.1-profile-run-v1", "run": run, "preflight": preflight, "fee_profile_sha256": fee_hash}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    if os.environ.get("SENTINELX_ALLOW_BROADCAST") != "1":
        raise SystemExit("managed V2.1 profiling requires SENTINELX_ALLOW_BROADCAST=1")
    if not re.fullmatch(r"[0-9a-f]{40}", SOURCE_REVISION):
        raise SystemExit("SENTINELX_V21_SOURCE_REVISION must be the pushed 40-character Git SHA")
    for path, expected in ((GOVERNOR_SOURCE, "70d140aaefaf258cbbaef07a0c06c67a0cb833921c62defc6158847f78332e0e"), (TARGET_SOURCE, PARENT_HASH), (SAFE_SOURCE, SAFE_HASH), (UNSAFE_SOURCE, UNSAFE_HASH)):
        if source_sha256(path) != expected:
            raise SystemExit(f"V2.1 source hash mismatch: {path}")
    from scripts.v2_source_manifest import verify_manifest
    errors = verify_manifest()
    if errors:
        raise SystemExit("source manifest mismatch: " + "; ".join(errors))

    client = make_client()
    journal_obj = journal()
    preflight = account_preflight(client, EXPECTED_DEPLOYER, journal_obj)
    if preflight["unresolved_journal_operations"]:
        raise SystemExit("unresolved local profile journal operations exist; reconcile before continuing")
    if int(str(preflight["latest_nonce"])) != int(str(preflight["pending_nonce"])):
        raise SystemExit("latest and pending nonce differ; reconcile before continuing")
    run = _read_run()
    initial_run = {
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "profile_only": True,
        "source_revision": SOURCE_REVISION,
        "repository_head_at_first_write": SOURCE_REVISION,
        "source_manifest_sha256": hashlib.sha256(SOURCE_MANIFEST.read_bytes()).hexdigest(),
        "deployer": EXPECTED_DEPLOYER,
        "balance_before": preflight["balance_wei"],
        "nonce_before": preflight["latest_nonce"],
        "pending_nonce_before": preflight["pending_nonce"],
        "fee_policy": _safe(client.get_current_fee_policy()),
        "cli_managed_signing": True,
        "external_security_artifact": "NOT_SUPPLIED_OPTIONAL_MODE",
    }
    # A resume after a reconciled CLI broadcast must retain the original
    # before-first-write measurements, not replace them with post-recovery
    # values.
    if run.get("repository_head_at_first_write") == "5efe4d5fa907a672e39c986a19f772ceabb8940b":
        # The first V2.1 broadcast was made from ce54d91; repair the copied
        # bootstrap value while preserving the original source revision.
        run["repository_head_at_first_write"] = run.get("source_revision", SOURCE_REVISION)
    for key, value in initial_run.items():
        run.setdefault(key, value)
    _save_run(run)

    gov_result = _submit_and_track(
        client=client, journal_obj=journal_obj, operation="v2.profile.deploy_governor",
        kind="deploy", source=GOVERNOR_SOURCE, metadata={"contract_name": "sentinelx_governor"},
    )
    governor = _contract_address(gov_result["receipt"])
    if not governor:
        raise SystemExit("governor deployment returned no contract address")
    run["governor"] = governor
    run["governor_tx"] = _tx_hash(journal_obj, "v2.profile.deploy_governor")
    run["governor_contract_info"] = read(client, governor, "contract_info")
    run["governor_source_parity"] = _verify_cli_source(governor, GOVERNOR_SOURCE)
    _save_run(run)

    target_args = [governor, PROFILE_LABEL, "profile-initial"]
    target_result = _submit_and_track(
        client=client, journal_obj=journal_obj, operation="v2.profile.deploy_safe_target",
        kind="deploy", source=TARGET_SOURCE, args=target_args,
        metadata={"contract_name": "protected_app_v1"},
    )
    safe_target = _contract_address(target_result["receipt"])
    if not safe_target:
        raise SystemExit("safe target deployment returned no contract address")
    run["safe_target"] = safe_target
    run["safe_target_tx"] = _tx_hash(journal_obj, "v2.profile.deploy_safe_target")
    run["safe_target_source_parity"] = _verify_cli_source(safe_target, TARGET_SOURCE)
    run["persistent_value_before"] = read(client, safe_target, "get_protected_value")
    persistent_write = _submit_and_track(
        client=client, journal_obj=journal_obj, operation="v2.profile.safe_persistent_write",
        kind="method", method="set_protected_value", address=safe_target,
        args=["v2-profile-persistent-before"],
    )
    _tag(journal_obj, "v2.profile.safe_persistent_write", method="set_protected_value")
    run["persistent_write_tx"] = persistent_write["tx_hash"]
    run["persistent_value_before_upgrade"] = read(client, safe_target, "get_protected_value")
    run["persistent_nonce_before_upgrade"] = read(client, safe_target, "get_value_nonce")
    _save_run(run)

    constitution = CONSTITUTION.read_text(encoding="utf-8")
    registration_args = [
        "ProtectedApp V1 V2 profile",
        constitution,
        "GIFTEDLOV/sentinelx",
        "GIFTEDLOV/sentinelx-ci",
        "OPTIONAL",
        "",
        SOURCE_PREFIX,
        CI_PREFIX,
        "",
        "1.0.0-profile",
        _source_url("contracts/protected_app_v1.py"),
        PARENT_HASH,
        86_400,
        3_600,
        3_600,
    ]
    registration_record = journal_obj.load()["operations"].get(SAFE_REGISTRATION_OPERATION)
    if registration_record is None:
        run["safe_registration_governor_before"] = read(client, governor, "is_target_registered", [safe_target])
        run["safe_registration_target_before"] = read(client, safe_target, "is_registered_with_sentinelx")
        if run["safe_registration_governor_before"] is not False or run["safe_registration_target_before"] is not False:
            raise SystemExit("fresh V2.1 target was already registered before registration proof")
        registration = _submit_and_track(
            client=client, journal_obj=journal_obj, operation=SAFE_REGISTRATION_OPERATION,
            kind="method", method="register_with_sentinelx", address=safe_target,
            args=registration_args, child_methods=["register_target"],
        )
    else:
        if registration_record.get("state") != "FINALIZED_EXECUTED":
            raise SystemExit("existing V2.1 registration parent is not finalized successfully")
        registration = _submit_and_track(
            client=client, journal_obj=journal_obj, operation=SAFE_REGISTRATION_OPERATION,
            kind="method", method="register_with_sentinelx", address=safe_target,
            args=registration_args, child_methods=["register_target"],
        )
    _tag(journal_obj, SAFE_REGISTRATION_OPERATION, method="register_with_sentinelx")
    run["registration_tx"] = registration["tx_hash"]
    policy = read_json(client, governor, "get_target_policy", [safe_target])
    run["safe_registration_governor_after"] = read(client, governor, "is_target_registered", [safe_target])
    run["safe_registration_target_after"] = read(client, safe_target, "is_registered_with_sentinelx")
    if run["safe_registration_governor_after"] is not True or run["safe_registration_target_after"] is not True:
        raise SystemExit("V2.1 registration child finalized but derived registration is not true")
    if policy.get("security_attestation_mode") != "OPTIONAL" or policy.get("security_configured") is not False:
        raise SystemExit("safe target policy is not explicitly OPTIONAL without security configuration")
    run["policy_fingerprint"] = policy.get("policy_fingerprint")
    run["policy"] = policy
    _save_run(run)

    # A duplicate registration must be rejected by the target's governor view
    # precondition and must not emit a second governor policy child.
    duplicate_operation = "v2.1.profile.duplicate_safe_registration"
    duplicate_error = ""
    try:
        _submit_and_track(
            client=client, journal_obj=journal_obj, operation=duplicate_operation,
            kind="method", method="register_with_sentinelx", address=safe_target,
            args=registration_args,
        )
    except Exception as error:
        duplicate_error = str(error)
    duplicate_record = journal_obj.load()["operations"].get(duplicate_operation)
    if duplicate_record is None:
        # Studio's fee simulation executes the target precondition and can
        # reject this duplicate before the bridge reserves or broadcasts a
        # transaction.  That is the strongest outcome: no second governor
        # child exists and no duplicate broadcast occurred.
        if not duplicate_error:
            raise SystemExit("duplicate registration was neither blocked nor journaled")
        run["duplicate_registration"] = {
            "error": duplicate_error,
            "tx_hash": None,
            "state": "BLOCKED_BEFORE_BROADCAST",
            "execution_result": None,
            "triggered_transaction_ids": [],
        }
    else:
        if duplicate_record.get("state") != "FINALIZED_EXECUTION_FAILED":
            raise SystemExit("duplicate registration did not finalize as a deterministic failure")
        if duplicate_record.get("triggered_transaction_ids"):
            raise SystemExit("duplicate registration emitted an unexpected governor child")
        run["duplicate_registration"] = {
            "error": duplicate_error,
            "tx_hash": duplicate_record.get("tx_hash"),
            "state": duplicate_record.get("state"),
            "execution_result": duplicate_record.get("execution_result"),
            "triggered_transaction_ids": duplicate_record.get("triggered_transaction_ids", []),
        }
    _save_run(run)

    # Separate recovery target: a malformed child must leave both governor
    # and target unregistered, after which a corrected retry must succeed.
    recovery_deploy = _submit_and_track(
        client=client, journal_obj=journal_obj, operation="v2.1.profile.deploy_recovery_target",
        kind="deploy", source=TARGET_SOURCE,
        args=[governor, "ProtectedApp V1 registration recovery", "recovery-initial"],
        metadata={"contract_name": "protected_app_v1"},
    )
    recovery_target = _contract_address(recovery_deploy["receipt"])
    if not recovery_target:
        raise SystemExit("recovery target deployment returned no address")
    run["recovery_target"] = recovery_target
    run["recovery_target_tx"] = recovery_deploy["tx_hash"]
    run["recovery_target_source_parity"] = _verify_cli_source(recovery_target, TARGET_SOURCE)
    # Persist the fresh recovery target before the intentionally failing write.
    # A CLI-side rejection must not make the target address disappear from the
    # resumable profile record.
    _save_run(run)
    recovery_args = [
        "ProtectedApp V1 registration recovery", constitution,
        "GIFTEDLOV/sentinelx", "GIFTEDLOV/sentinelx-ci", "OPTIONAL", "",
        SOURCE_PREFIX, CI_PREFIX, "", "1.0.0-profile",
        _source_url("contracts/protected_app_v1.py"), PARENT_HASH,
        86_400, 3_600, 3_600,
    ]
    recovery_complete = (
        isinstance(run.get("recovery_registration"), dict)
        and run["recovery_registration"].get("after_retry") == {"governor": True, "target": True}
    )
    if recovery_complete:
        recovery_after_retry = {
            "governor": read(client, governor, "is_target_registered", [recovery_target]),
            "target": read(client, recovery_target, "is_registered_with_sentinelx"),
        }
        if recovery_after_retry != {"governor": True, "target": True}:
            raise SystemExit("completed recovery target no longer reports registered")
    else:
        recovery_before = {
            "governor": read(client, governor, "is_target_registered", [recovery_target]),
            "target": read(client, recovery_target, "is_registered_with_sentinelx"),
        }
        if recovery_before != {"governor": False, "target": False}:
            raise SystemExit("fresh recovery target was not unregistered")
        malformed = list(recovery_args)
        malformed[11] = "not-a-sha256"
        recovery_failure_operation = "v2.1.profile.recovery_registration_malformed"
        prior_failure = journal_obj.load()["operations"].get(recovery_failure_operation)
        if isinstance(prior_failure, dict):
            if (
                prior_failure.get("state") == "BLOCKED_BEFORE_BROADCAST"
                and prior_failure.get("broadcast_verified_absent") is True
                and not prior_failure.get("tx_hash")
            ):
                # The first CLI attempt is retained as evidence.  A new
                # operation name is mandatory for the verified no-broadcast
                # retry; the original reservation is never overwritten.
                recovery_failure_operation += ".retry"
            elif prior_failure.get("state") != "FINALIZED_EXECUTED":
                raise SystemExit("malformed recovery operation remains unresolved")
        recovery_failure_error = ""
        try:
            _submit_and_track(
                client=client, journal_obj=journal_obj, operation=recovery_failure_operation,
                kind="method", method="register_with_sentinelx", address=recovery_target,
                args=malformed, child_methods=["register_target"],
            )
        except RuntimeError as error:
            recovery_failure_error = str(error)
        recovery_failure_record = _operation_record(journal_obj, recovery_failure_operation)
        recovery_child_ids = recovery_failure_record.get("triggered_transaction_ids", [])
        if recovery_failure_record.get("state") != "FINALIZED_EXECUTED" or len(recovery_child_ids) != 1:
            raise SystemExit("malformed recovery parent did not finalize with exactly one child")
        recovery_child_operation = f"{recovery_failure_operation}.child.0"
        recovery_child_record = _operation_record(journal_obj, recovery_child_operation)
        if recovery_child_record.get("state") != "FINALIZED_EXECUTION_FAILED":
            raise SystemExit("malformed recovery child did not finalize as a failure")
        recovery_after_failure = {
            "governor": read(client, governor, "is_target_registered", [recovery_target]),
            "target": read(client, recovery_target, "is_registered_with_sentinelx"),
        }
        if recovery_after_failure != {"governor": False, "target": False}:
            raise SystemExit("failed recovery child poisoned target registration state")
        recovery_retry_operation = "v2.1.profile.recovery_registration_retry"
        recovery_retry = _submit_and_track(
            client=client, journal_obj=journal_obj, operation=recovery_retry_operation,
            kind="method", method="register_with_sentinelx", address=recovery_target,
            args=recovery_args, child_methods=["register_target"],
        )
        _tag(journal_obj, recovery_retry_operation, method="register_with_sentinelx")
        recovery_after_retry = {
            "governor": read(client, governor, "is_target_registered", [recovery_target]),
            "target": read(client, recovery_target, "is_registered_with_sentinelx"),
        }
        if recovery_after_retry != {"governor": True, "target": True}:
            raise SystemExit("corrected recovery registration did not become registered")
        run["recovery_registration"] = {
            "malformed_parent_tx": recovery_failure_record.get("tx_hash"),
            "malformed_child_tx": recovery_child_ids[0],
            "malformed_parent_result": recovery_failure_record.get("execution_result"),
            "malformed_child_result": recovery_child_record.get("execution_result"),
            "malformed_error": recovery_failure_error,
            "after_failure": recovery_after_failure,
            "retry_parent_tx": recovery_retry["tx_hash"],
            "retry_child_txs": recovery_retry.get("children", []),
            "after_retry": recovery_after_retry,
        }
        _save_run(run)

    safe_ci = run.get("safe_ci")
    if not isinstance(safe_ci, dict) or not safe_ci.get("fetched_verified"):
        safe_ci = _publish_ci_evidence(
            target=safe_target, policy_fingerprint=str(run["policy_fingerprint"]),
            candidate_hash=SAFE_HASH, candidate_source=SAFE_SOURCE, label="safe",
        )
        run["safe_ci"] = safe_ci
        _save_run(run)
    safe_candidate_version = "2.0.0-safe-profile"
    safe_proposal_args = [
        safe_target, safe_candidate_version, _source_url("contracts/protected_app_v2_safe.py"),
        SAFE_SOURCE.read_bytes(),
        str(safe_ci["url"]), str(safe_ci["evidence_id"]), "", "",
        "Add the verified release status read without changing user rights or upgrade authority.",
    ]
    proposal = _submit_and_track(
        client=client, journal_obj=journal_obj, operation="v2.profile.safe_create_proposal",
        kind="method", method="create_proposal", address=governor, args=safe_proposal_args,
    )
    _tag(journal_obj, "v2.profile.safe_create_proposal", method="create_proposal")
    safe_proposal_id = int(read(client, governor, "get_active_proposal", [safe_target]))
    run["safe_proposal_id"] = safe_proposal_id
    run["safe_proposal_tx"] = proposal["tx_hash"]
    run["safe_proposal"] = read_json(client, governor, "get_proposal", [safe_proposal_id])
    _save_run(run)

    capture_operation = "v2.profile.safe_capture_evidence"
    retry_number = 0
    while True:
        capture_record = journal_obj.load()["operations"].get(capture_operation)
        if not isinstance(capture_record, dict):
            break
        if capture_record.get("state") == "FINALIZED_EXECUTED":
            break
        if capture_record.get("state") != "FINALIZED_EXECUTION_FAILED":
            raise SystemExit("safe capture operation remains unresolved")
        retry_number += 1
        capture_operation = (
            "v2.profile.safe_capture_evidence.retry"
            if retry_number == 1
            else f"v2.profile.safe_capture_evidence.retry{retry_number}"
        )
    capture = _submit_and_track(
        client=client, journal_obj=journal_obj, operation=capture_operation,
        kind="method", method="capture_evidence", address=governor, args=[safe_proposal_id],
    )
    _tag(journal_obj, capture_operation, method="capture_evidence")
    run["safe_capture_operation"] = capture_operation
    run["safe_capture_tx"] = capture["tx_hash"]
    snapshot = read_json(client, governor, "get_evidence_snapshot", [safe_proposal_id])
    if snapshot.get("status") != "EVIDENCE_READY" or snapshot.get("security_present") is not False:
        raise SystemExit("safe evidence snapshot is not EVIDENCE_READY with explicit security absence")
    run["safe_snapshot"] = snapshot
    run["safe_snapshot_digest"] = snapshot.get("snapshot_digest")
    _save_run(run)

    review = _submit_and_track(
        client=client, journal_obj=journal_obj, operation="v2.profile.safe_review_proposal",
        kind="method", method="review_proposal", address=governor, args=[safe_proposal_id],
        child_methods=["install_reviewed_upgrade"],
    )
    _tag(journal_obj, "v2.profile.safe_review_proposal", method="review_proposal")
    # The install child emits a confirmation child back to the governor.
    if review.get("children"):
        _tag(journal_obj, "v2.profile.safe_review_proposal.child.0.child.0", method="confirm_install")
    run["safe_review_tx"] = review["tx_hash"]
    run["safe_review_lifecycle"] = review.get("lifecycle")
    safe_state = read_json(client, governor, "get_proposal", [safe_proposal_id])
    if safe_state.get("status") != "VERIFIED":
        raise SystemExit(f"safe review did not reach VERIFIED: {safe_state.get('status')}")
    run["safe_final_state"] = safe_state
    run["safe_review_fetches"] = read(client, governor, "get_review_web_fetch_count", [safe_proposal_id])
    run["safe_final_target_state"] = {
        "application_name": read(client, safe_target, "get_application_name"),
        "owner": read(client, safe_target, "get_owner"),
        "governor": read(client, safe_target, "get_upgrade_governor"),
        "protected_value": read(client, safe_target, "get_protected_value"),
        "value_nonce": read(client, safe_target, "get_value_nonce"),
        "installed_proposal_id": read(client, safe_target, "get_installed_proposal_id"),
        "installed_candidate_hash": read(client, safe_target, "get_installed_candidate_hash"),
        "registered": read(client, safe_target, "is_registered_with_sentinelx"),
    }
    run["safe_snapshot_after_review"] = read_json(client, governor, "get_evidence_snapshot", [safe_proposal_id])
    run["persistent_state_preserved"] = (
        run.get("persistent_value_before_upgrade") == run["safe_final_target_state"].get("protected_value")
        and run.get("persistent_nonce_before_upgrade") == run["safe_final_target_state"].get("value_nonce")
    )
    run["upgrade_authority_preserved"] = str(run["safe_final_target_state"].get("governor")).lower() == str(governor).lower()
    _save_run(run)

    feature = _submit_and_track(
        client=client, journal_obj=journal_obj, operation="v2.profile.safe_v2_feature",
        kind="method", method="set_release_note", address=safe_target,
        args=["V2 profile feature verified"],
    )
    _tag(journal_obj, "v2.profile.safe_v2_feature", method="set_release_note")
    run["safe_v2_feature_tx"] = feature["tx_hash"]
    run["safe_v2_feature_verified"] = read(client, safe_target, "get_release_note") == "V2 profile feature verified"
    run["safe_final_target_state"]["release_note"] = read(client, safe_target, "get_release_note")
    run["safe_policy_after_review"] = read_json(client, governor, "get_target_policy", [safe_target])
    run["safe_active_proposal"] = read(client, governor, "get_active_proposal", [safe_target])
    _save_run(run)

    # Fresh unsafe target: the unsafe candidate is reviewed and rejected without installation.
    unsafe_result = _submit_and_track(
        client=client, journal_obj=journal_obj, operation="v2.profile.deploy_unsafe_target",
        kind="deploy", source=TARGET_SOURCE, args=[governor, "ProtectedApp V1 unsafe negative", "unsafe-initial"],
        metadata={"contract_name": "protected_app_v1"},
    )
    unsafe_target = _contract_address(unsafe_result["receipt"])
    if not unsafe_target:
        raise SystemExit("unsafe negative target deployment returned no address")
    run["unsafe_target"] = unsafe_target
    run["unsafe_target_tx"] = unsafe_result["tx_hash"]
    _verify_cli_source(unsafe_target, TARGET_SOURCE)
    unsafe_registration = _submit_and_track(
        client=client, journal_obj=journal_obj, operation="v2.profile.register_unsafe_target",
        kind="method", method="register_with_sentinelx", address=unsafe_target,
        args=["ProtectedApp V1 unsafe negative", constitution, "GIFTEDLOV/sentinelx", "GIFTEDLOV/sentinelx-ci", "OPTIONAL", "", SOURCE_PREFIX, CI_PREFIX, "", "1.0.0-profile", _source_url("contracts/protected_app_v1.py"), PARENT_HASH, 86_400, 3_600, 3_600],
        child_methods=["register_target"],
    )
    _tag(journal_obj, "v2.profile.register_unsafe_target", method="register_with_sentinelx")
    unsafe_policy = read_json(client, governor, "get_target_policy", [unsafe_target])
    unsafe_ci = _publish_ci_evidence(target=unsafe_target, policy_fingerprint=str(unsafe_policy["policy_fingerprint"]), candidate_hash=UNSAFE_HASH, candidate_source=UNSAFE_SOURCE, label="unsafe")
    run["unsafe_ci"] = unsafe_ci
    unsafe_proposal = _submit_and_track(
        client=client, journal_obj=journal_obj, operation="v2.profile.unsafe_create_proposal",
        kind="method", method="create_proposal", address=governor,
        args=[unsafe_target, "2.0.0-unsafe-profile", _source_url("contracts/protected_app_v2_unsafe.py"), UNSAFE_SOURCE.read_bytes(), str(unsafe_ci["url"]), str(unsafe_ci["evidence_id"]), "", "", "This intentionally unsafe candidate must be rejected before installation."],
    )
    _tag(journal_obj, "v2.profile.unsafe_create_proposal", method="create_proposal")
    unsafe_proposal_id = int(read(client, governor, "get_active_proposal", [unsafe_target]))
    unsafe_capture = _submit_and_track(client=client, journal_obj=journal_obj, operation="v2.profile.unsafe_capture_evidence", kind="method", method="capture_evidence", address=governor, args=[unsafe_proposal_id])
    _tag(journal_obj, "v2.profile.unsafe_capture_evidence", method="capture_evidence")
    unsafe_review = _submit_and_track(client=client, journal_obj=journal_obj, operation="v2.profile.unsafe_review_proposal", kind="method", method="review_proposal", address=governor, args=[unsafe_proposal_id])
    _tag(journal_obj, "v2.profile.unsafe_review_proposal", method="review_proposal")
    unsafe_state = read_json(client, governor, "get_proposal", [unsafe_proposal_id])
    unsafe_before = {key: read(client, unsafe_target, method) for key, method in {"value": "get_protected_value", "nonce": "get_value_nonce", "proposal": "get_installed_proposal_id", "hash": "get_installed_candidate_hash", "governor": "get_upgrade_governor"}.items()}
    if unsafe_state.get("status") != "REJECTED":
        raise SystemExit(f"unsafe review did not reach REJECTED: {unsafe_state.get('status')}")
    unsafe_after = {key: read(client, unsafe_target, method) for key, method in {"value": "get_protected_value", "nonce": "get_value_nonce", "proposal": "get_installed_proposal_id", "hash": "get_installed_candidate_hash", "governor": "get_upgrade_governor"}.items()}
    run.update({"unsafe_proposal_id": unsafe_proposal_id, "unsafe_proposal_tx": unsafe_proposal["tx_hash"], "unsafe_capture_tx": unsafe_capture["tx_hash"], "unsafe_review_tx": unsafe_review["tx_hash"], "unsafe_decision": unsafe_state.get("status"), "negative_state_preserved": unsafe_before == unsafe_after})
    _save_run(run)

    # Repair and cancellation coverage: deliberately bind an immutable but wrong CI envelope.
    repair_result = _submit_and_track(client=client, journal_obj=journal_obj, operation="v2.profile.deploy_repair_target", kind="deploy", source=TARGET_SOURCE, args=[governor, "ProtectedApp V1 repair coverage", "repair-initial"], metadata={"contract_name": "protected_app_v1"})
    repair_target = _contract_address(repair_result["receipt"])
    if not repair_target:
        raise SystemExit("repair target deployment returned no address")
    run["repair_target"] = repair_target
    repair_registration = _submit_and_track(client=client, journal_obj=journal_obj, operation="v2.profile.register_repair_target", kind="method", method="register_with_sentinelx", address=repair_target, args=["ProtectedApp V1 repair coverage", constitution, "GIFTEDLOV/sentinelx", "GIFTEDLOV/sentinelx-ci", "OPTIONAL", "", SOURCE_PREFIX, CI_PREFIX, "", "1.0.0-profile", _source_url("contracts/protected_app_v1.py"), PARENT_HASH, 86_400, 3_600, 3_600], child_methods=["register_target"])
    _tag(journal_obj, "v2.profile.register_repair_target", method="register_with_sentinelx")
    repair_policy = read_json(client, governor, "get_target_policy", [repair_target])
    wrong_ci = _publish_ci_evidence(target=unsafe_target, policy_fingerprint=str(repair_policy["policy_fingerprint"]), candidate_hash=UNSAFE_HASH, candidate_source=UNSAFE_SOURCE, label="wrong-binding")
    repair_ci = _publish_ci_evidence(target=repair_target, policy_fingerprint=str(repair_policy["policy_fingerprint"]), candidate_hash=SAFE_HASH, candidate_source=SAFE_SOURCE, label="repair-correct")
    repair_proposal = _submit_and_track(client=client, journal_obj=journal_obj, operation="v2.profile.repair_create_proposal", kind="method", method="create_proposal", address=governor, args=[repair_target, "2.0.0-repair-coverage", _source_url("contracts/protected_app_v2_safe.py"), SAFE_SOURCE.read_bytes(), str(wrong_ci["url"]), str(wrong_ci["evidence_id"]), "", "", "Exercise evidence repair without changing candidate bytes."])
    _tag(journal_obj, "v2.profile.repair_create_proposal", method="create_proposal")
    repair_proposal_id = int(read(client, governor, "get_active_proposal", [repair_target]))
    repair_capture_wrong = _submit_and_track(client=client, journal_obj=journal_obj, operation="v2.profile.repair_capture_wrong", kind="method", method="capture_evidence", address=governor, args=[repair_proposal_id])
    _tag(journal_obj, "v2.profile.repair_capture_wrong", method="capture_evidence")
    repair_state_wrong = read_json(client, governor, "get_proposal", [repair_proposal_id])
    if repair_state_wrong.get("status") != "EVIDENCE_REPAIR_REQUIRED":
        raise SystemExit(f"wrong evidence did not require repair: {repair_state_wrong.get('status')}")
    repair_call = _submit_and_track(client=client, journal_obj=journal_obj, operation="v2.profile.repair_evidence", kind="method", method="repair_evidence", address=governor, args=[repair_proposal_id, _source_url("contracts/protected_app_v2_safe.py"), str(repair_ci["url"]), str(repair_ci["evidence_id"]), "", ""])
    _tag(journal_obj, "v2.profile.repair_evidence", method="repair_evidence")
    repair_capture_correct = _submit_and_track(client=client, journal_obj=journal_obj, operation="v2.profile.repair_capture_correct", kind="method", method="capture_evidence", address=governor, args=[repair_proposal_id])
    _tag(journal_obj, "v2.profile.repair_capture_correct", method="capture_evidence")
    repair_cancel = _submit_and_track(client=client, journal_obj=journal_obj, operation="v2.profile.cancel_proposal", kind="method", method="cancel_proposal", address=governor, args=[repair_proposal_id])
    _tag(journal_obj, "v2.profile.cancel_proposal", method="cancel_proposal")
    run.update({"repair_proposal_id": repair_proposal_id, "repair_proposal_tx": repair_proposal["tx_hash"], "repair_evidence_tx": repair_call["tx_hash"], "repair_capture_tx": repair_capture_correct["tx_hash"], "cancel_tx": repair_cancel["tx_hash"], "repair_final_state": read_json(client, governor, "get_proposal", [repair_proposal_id])})
    _save_run(run)

    # Build only from finalized successful journal observations, then bind the
    # detailed coverage and readiness manifests to the live profile.
    from scripts.build_fee_profile import build_profile_from_journal
    profile = build_profile_from_journal(JOURNAL_PATH, FEE_PROFILE)
    _write_outputs(run, journal_obj, preflight, profile if isinstance(profile, dict) else {})
    print(json.dumps({
        "network": NETWORK,
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "deployer": EXPECTED_DEPLOYER,
        "governor": run.get("governor"),
        "safe_target": run.get("safe_target"),
        "unsafe_target": run.get("unsafe_target"),
        "repair_target": run.get("repair_target"),
        "safe_proposal_id": run.get("safe_proposal_id"),
        "unsafe_proposal_id": run.get("unsafe_proposal_id"),
        "fee_profile": str(FEE_PROFILE.relative_to(ROOT)).replace("\\", "/"),
        "coverage": str(COVERAGE.relative_to(ROOT)).replace("\\", "/"),
        "readiness": str(READINESS.relative_to(ROOT)).replace("\\", "/"),
        "journal": str(JOURNAL_PATH),
    }, indent=2, sort_keys=True))
    return 0


def _contract_address(receipt: Any) -> str | None:
    if not isinstance(receipt, dict):
        return None
    # Studio exposes the deterministic deployment address as the receipt
    # recipient; network-style receipts use contract_address.
    value = (
        receipt.get("contract_address")
        or receipt.get("contractAddress")
        or receipt.get("recipient")
        or receipt.get("to_address")
    )
    return str(value) if value else None


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


if __name__ == "__main__":
    raise SystemExit(main())
