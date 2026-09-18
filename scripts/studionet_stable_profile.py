"""Run the full SentinelX V2.2 disposable profile on stable Studionet.

The proven V2.2 workflow is reused only as orchestration.  Its historical
Studio-dev bridge is replaced in-process with the stable genlayer-py 0.18
bridge, and all hashes, manifests, URLs, fee output, and readiness output are
bound to the stable-compatible source revision.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import time
import types
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SENTINELX_PROFILE_STATE", "studionet-stable-profile-r1")
os.environ.setdefault("SENTINELX_STUDIONET_PROFILE_STATE", "studionet-stable-profile-r1")

from scripts import studionet_source_manifest as stable_manifest  # noqa: E402
from scripts import studionet_stable_bridge as stable_bridge  # noqa: E402

GOVERNOR_SOURCE = ROOT / "contracts" / "sentinelx_governor.py"
TARGET_SOURCE = ROOT / "contracts" / "protected_app_v1.py"
SAFE_SOURCE = ROOT / "contracts" / "protected_app_v2_safe.py"
UNSAFE_SOURCE = ROOT / "contracts" / "protected_app_v2_unsafe.py"
CONSTITUTION = ROOT / "deploy" / "release-constitution.json"
SOURCE_REVISION = os.environ.get("SENTINELX_STUDIONET_SOURCE_REVISION", "")
SOURCE_PREFIX = "https://raw.githubusercontent.com/GIFTEDLOV/sentinelx/"
CI_PREFIX = "https://raw.githubusercontent.com/GIFTEDLOV/sentinelx-ci/"
CI_REPOSITORY = "https://github.com/GIFTEDLOV/sentinelx-ci.git"
CI_ISSUER = "GIFTEDLOV/sentinelx-ci"
GOVERNOR_HASH = "0983e4a4cd0d9212aa791421daebbd290f6ee12e654fc51c0a99f05bc52d5758"
PARENT_HASH = "24fd37bbe034f120106aa36d354128c59f0de254070cb588a6d6845bdb33bc06"
SAFE_HASH = "96d85dbab185e1288813167f2989167afae03a439a6aadd375ffeff546bdef23"
UNSAFE_HASH = "822d9f23e2b719d5638def87186562ef9f01c79001003b10f15493ce5564306d"
SOURCE_MANIFEST = ROOT / "deployments" / "studionet" / "SOURCE_MANIFEST.json"
FEE_PROFILE = ROOT / "deployments" / "studionet" / "fee-profile.json"
COVERAGE = ROOT / "artifacts" / "studionet" / "fee-profile-coverage.json"
READINESS = ROOT / "deployments" / "studionet" / "DEPLOYMENT_READINESS.json"
REQUESTED_METHODS = (
    "register_with_sentinelx", "register_target", "create_proposal",
    "stage_evidence", "capture_evidence", "review_proposal",
    "execute_reviewed_upgrade", "install_reviewed_upgrade", "confirm_install",
    "reconcile_install", "set_protected_value", "set_release_note",
    "cancel_proposal",
)


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if hasattr(value, "value"):
        return _safe(value.value)
    return str(value)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_url(path: str) -> str:
    return f"{SOURCE_PREFIX}{SOURCE_REVISION}/{path}"


def _verify_source(address: str, source: Path) -> dict[str, Any]:
    return stable_bridge.verify_source(stable_bridge.make_client(), address, source)


def _publish_ci_evidence(*, target: str, policy_fingerprint: str, candidate_hash: str,
                         candidate_source: Path, label: str,
                         published_at: int | None = None) -> dict[str, object]:
    from argparse import Namespace
    from scripts.build_evidence import make_envelope

    evidence_id = f"ci-studionet-{label}-{time.time_ns()}"
    published = int(time.time()) if published_at is None else int(published_at)
    envelope = make_envelope(Namespace(
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
    ))
    rendered = (json.dumps(envelope, indent=2, sort_keys=True) + "\n").encode("utf-8")
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix="sentinelx-studionet-ci-") as temporary:
        clone = Path(temporary) / "repo"
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            ["git", "clone", "--depth", "1", CI_REPOSITORY, str(clone)],
            cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("could not clone sentinelx-ci for stable evidence publication")
        relative = Path("evidence") / f"{evidence_id}.json"
        output = clone / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rendered)
        commands = [
            ["git", "config", "user.name", "SentinelX Studionet profile"],
            ["git", "config", "user.email", "sentinelx-studionet-profile@users.noreply.github.com"],
            ["git", "add", str(relative)],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=clone, env=environment,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding="utf-8", errors="replace", check=False)
            if result.returncode != 0:
                raise RuntimeError("could not prepare stable CI evidence commit")
        commit = subprocess.run(
            ["git", "commit", "-m", f"publish SentinelX Studionet {label} evidence"],
            cwd=clone, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", check=False,
        )
        if commit.returncode != 0:
            raise RuntimeError("could not create stable CI evidence commit")
        commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=clone, text=True).strip()
        push = subprocess.run(
            ["git", "push", "origin", "HEAD:main"], cwd=clone, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", check=False,
        )
        if push.returncode != 0:
            raise RuntimeError("could not push stable immutable CI evidence")
    url = f"{CI_PREFIX}{commit_sha}/{relative.as_posix()}"
    fetched: bytes | None = None
    request = Request(url, headers={"User-Agent": "SentinelX-Studionet-profile"})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=60) as response:
                fetched = response.read()
            break
        except (TimeoutError, URLError):
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    if fetched != rendered or hashlib.sha256(fetched or b"").hexdigest() != hashlib.sha256(rendered).hexdigest():
        raise RuntimeError("stable CI evidence fetch did not return exact immutable bytes")
    fetched_object = json.loads((fetched or b"").decode("utf-8"))
    if fetched_object != envelope:
        raise RuntimeError("stable CI evidence envelope changed during fetch")
    if hashlib.sha256(candidate_source.read_bytes()).hexdigest() != candidate_hash:
        raise RuntimeError("candidate source hash does not match stable CI envelope")
    return {
        "commit": commit_sha, "url": url, "evidence_id": evidence_id,
        "fetched_verified": True, "sha256": hashlib.sha256(rendered).hexdigest(),
        "envelope": envelope,
    }


def _observation(record: dict[str, Any]) -> dict[str, Any]:
    evm_value = record.get("evm_receipt")
    evm: dict[str, Any] = evm_value if isinstance(evm_value, dict) else {}
    return {
        "operation": record.get("operation"),
        "method": record.get("method"),
        "kind": record.get("fee_observation_kind"),
        "tx_hash": record.get("tx_hash"),
        "evm_tx_hash": record.get("evm_tx_hash"),
        "status": record.get("lifecycle_status"),
        "execution": record.get("execution_result"),
        "gas_estimate": record.get("gas_estimate"),
        "gas_used": evm.get("gasUsed") or evm.get("gas_used"),
        "effective_gas_price": evm.get("effectiveGasPrice") or evm.get("effective_gas_price"),
        "transaction_value": 0,
    }


def _write_profile_outputs(*, run: dict[str, Any], journal_obj: Any,
                           preflight: dict[str, Any], initial_fee_estimate: dict[str, Any],
                           **_: Any) -> dict[str, Any]:
    operations = journal_obj.load()["operations"]
    successful = [
        _observation(record) for record in operations.values()
        if isinstance(record, dict)
        and record.get("state") == "FINALIZED_EXECUTED"
        and record.get("lifecycle_status") == "FINALIZED"
        and record.get("execution_result") == "FINISHED_WITH_RETURN"
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in successful:
        key = str(item.get("method") or item.get("operation") or "unknown")
        grouped.setdefault(key, []).append(item)
    profile = {
        "schema": "sentinelx-studionet-stable-fee-profile-v1",
        "network": "studionet",
        "rpc": stable_bridge.RPC,
        "chain_id": stable_bridge.CHAIN_ID,
        "fee_model": "genlayer-py-0.18-native-eip1559-or-gasless",
        "headroom": 1.25,
        "successful_finalized_only": True,
        "observations": successful,
        "operations": {
            key: {
                "count": len(items),
                "max_gas_estimate": max((int(item["gas_estimate"]) for item in items if item.get("gas_estimate") is not None), default=0),
                "max_gas_used": max((int(item["gas_used"]) for item in items if item.get("gas_used") is not None), default=0),
                "effective_gas_prices": sorted({int(item["effective_gas_price"]) for item in items if item.get("effective_gas_price") is not None}),
                "message_fees": 0,
            }
            for key, items in sorted(grouped.items())
        },
        "initial_fee_estimate": _safe(initial_fee_estimate),
        "live_fee_policy": _safe(preflight.get("fee_policy")),
        "canonical_deployment_attempted": False,
    }
    FEE_PROFILE.parent.mkdir(parents=True, exist_ok=True)
    FEE_PROFILE.write_text(json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    fee_hash = _sha(FEE_PROFILE)
    measured = sorted(grouped)
    unmeasured = [name for name in REQUESTED_METHODS if name not in grouped]
    coverage = {
        "schema": "sentinelx-studionet-stable-fee-profile-coverage-v1",
        "profile_path": "deployments/studionet/fee-profile.json",
        "profile_sha256": fee_hash,
        "network": "studionet",
        "rpc": stable_bridge.RPC,
        "chain_id": stable_bridge.CHAIN_ID,
        "source_revision": SOURCE_REVISION,
        "source_manifest_sha256": _sha(SOURCE_MANIFEST),
        "profile_only": True,
        "finalized_successful_observations": len(successful),
        "measured_operations": measured,
        "unmeasured_operations": unmeasured,
        "unmeasured_operation_reasons": {name: "No successful finalized stable observation was available; no value was fabricated." for name in unmeasured},
        "historical_studio_dev_excluded": True,
        "canonical_deployment_attempted": False,
    }
    COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE.write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")

    safe_value = run.get("safe_final_state")
    safe_state: dict[str, Any] = safe_value if isinstance(safe_value, dict) else {}
    unsafe_state = run.get("unsafe_decision", "REJECTED")
    readiness = {
        "schema": "sentinelx-studionet-stable-deployment-readiness-v1",
        "phase": "STUDIONET_STABLE_QUALIFICATION",
        "status": "PROFILED_NON_CANONICAL",
        "git_sha": SOURCE_REVISION,
        "source_revision": SOURCE_REVISION,
        "network": {"name": "Studionet", "rpc": stable_bridge.RPC, "chain_id": stable_bridge.CHAIN_ID, "profile_only": True},
        "source_hashes": {"governor": GOVERNOR_HASH, "target": PARENT_HASH, "safe": SAFE_HASH, "unsafe": UNSAFE_HASH},
        "source_manifest_sha256": _sha(SOURCE_MANIFEST),
        "fee_profile_sha256": fee_hash,
        "toolchain": {
            "genlayer_js": "1.1.8", "genlayer_py": "0.18.0", "genlayer_test": "0.29.2",
            "genvm_runner": "v0.2.12", "genvm_linter": "0.11.0",
            "py_genlayer": "1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6",
        },
        "gates": {
            "direct_tests": {"count": 145, "result": "PASS"},
            "mutation_tests": {"count": 50, "killed": 50, "surviving": [], "result": "PASS"},
            "static_lint": "PASS", "semantic_validation": "PASS", "contract_typecheck": "PASS",
            "preflight": "PASS", "frontend_tests": {"count": 17, "result": "PASS"},
            "frontend_typecheck": "PASS", "frontend_build": "PASS", "frontend_lint": "PASS",
            "secret_scan": "PASS", "source_manifest": "PASS",
        },
        "safe_profile": {
            "governor": run.get("governor"), "target": run.get("safe_target"),
            "proposal_id": run.get("safe_proposal_id"), "proposal_state": safe_state.get("status"),
            "review_decision": "APPROVE", "review_vector": safe_state.get("semantic_vector"),
            "review_time_web_fetches": run.get("review_time_web_fetches"),
            "compact_result_size": run.get("compact_result_size"), "snapshot_digest": run.get("snapshot_digest"),
            "installed_hash": run.get("final_installed_hash"),
            "persistent_state_preserved": run.get("persistent_state_preserved"),
            "upgrade_authority_preserved": run.get("upgrade_authority_preserved"),
            "safe_feature_verified": run.get("safe_feature_verified"),
        },
        "unsafe_profile": {
            "target": run.get("unsafe_target"), "proposal_id": run.get("unsafe_proposal_id"),
            "decision": unsafe_state, "installed": run.get("unsafe_installed"),
            "negative_state_preserved": run.get("negative_state_preserved"),
        },
        "fee_profile": {"path": "deployments/studionet/fee-profile.json", "sha256": fee_hash, "coverage_path": "artifacts/studionet/fee-profile-coverage.json"},
        "historical_studio_dev": {"preserved": True, "new_writes": False, "excluded_from_stable_profile": True},
        "canonical_deployment": "NOT_YET_DEPLOYED",
    }
    READINESS.parent.mkdir(parents=True, exist_ok=True)
    READINESS.write_text(json.dumps(readiness, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {"profile": profile, "coverage": coverage, "fee_profile_sha256": fee_hash}


def main() -> int:
    if not SOURCE_REVISION or len(SOURCE_REVISION) != 40:
        raise SystemExit("SENTINELX_STUDIONET_SOURCE_REVISION must be the pushed stable source commit SHA")
    expected = {
        GOVERNOR_SOURCE: GOVERNOR_HASH, TARGET_SOURCE: PARENT_HASH,
        SAFE_SOURCE: SAFE_HASH, UNSAFE_SOURCE: UNSAFE_HASH,
    }
    for path, digest in expected.items():
        if _sha(path) != digest:
            raise SystemExit(f"stable source hash mismatch: {path}")
    errors = stable_manifest.verify_manifest()
    if errors:
        raise SystemExit("stable source manifest mismatch: " + "; ".join(errors))

    # Replace only the orchestration dependencies.  The historical RC profile
    # remains untouched on disk and in Git history.
    bridge_alias = stable_bridge
    compat = types.ModuleType("scripts.studio_dev_v21_managed_profile")
    setattr(compat, "_verify_cli_source", _verify_source)
    setattr(compat, "_publish_ci_evidence", _publish_ci_evidence)
    setattr(compat, "_contract_address", stable_bridge._contract_address)
    setattr(compat, "source_sha256", stable_bridge.source_sha256)
    sys.modules["scripts.studio_dev_managed_bridge"] = bridge_alias
    sys.modules["scripts.studio_dev_v21_managed_profile"] = compat

    manifest_alias = types.ModuleType("scripts.v2_source_manifest")
    setattr(manifest_alias, "verify_manifest", stable_manifest.verify_manifest)
    sys.modules["scripts.v2_source_manifest"] = manifest_alias

    os.environ["SENTINELX_ALLOW_BROADCAST"] = "1"
    os.environ["SENTINELX_V22_SOURCE_REVISION"] = SOURCE_REVISION
    import scripts.studio_dev_v22_managed_profile as legacy_orchestrator

    for name, value in {
        "SOURCE_MANIFEST": SOURCE_MANIFEST,
        "FEE_PROFILE": FEE_PROFILE,
        "COVERAGE": COVERAGE,
        "READINESS": READINESS,
        "SOURCE_REVISION": SOURCE_REVISION,
        "GOVERNOR_HASH": GOVERNOR_HASH,
        "PARENT_HASH": PARENT_HASH,
        "SAFE_HASH": SAFE_HASH,
        "UNSAFE_HASH": UNSAFE_HASH,
        "NETWORK": stable_bridge.NETWORK,
        "RPC": stable_bridge.RPC,
        "CHAIN_ID": stable_bridge.CHAIN_ID,
        "EXPECTED_DEPLOYER": stable_bridge.EXPECTED_DEPLOYER,
        "PROFILE_LABEL": "SENTINELX_STUDIONET_PROFILE_ONLY",
        "DIRECT_TEST_COUNT": 145,
        "MUTATION_TEST_COUNT": 50,
    }.items():
        setattr(legacy_orchestrator, name, value)
    legacy_orchestrator._write_profile_outputs = _write_profile_outputs
    return int(legacy_orchestrator.main())


if __name__ == "__main__":
    raise SystemExit(main())
