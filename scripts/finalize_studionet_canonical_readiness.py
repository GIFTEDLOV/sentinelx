"""Bind canonical Studionet live proof into the readiness manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
READINESS = ROOT / "deployments" / "studionet" / "v2.3" / "DEPLOYMENT_READINESS.json"
MANIFEST = ROOT / "deployments" / "studionet" / "v2.3" / "CANONICAL_DEPLOYMENT.json"
PROOF = ROOT / "artifacts" / "studionet" / "v2.3" / "canonical-live-proof.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    readiness = json.loads(READINESS.read_text(encoding="utf-8"))
    proof = json.loads(PROOF.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if proof.get("result") != "PASS" or proof.get("final_proposal_state") != "VERIFIED":
        raise SystemExit("canonical live proof is not a successful VERIFIED release")
    if proof.get("review_web_fetches") != 0 or proof.get("compact_result_size") != 827:
        raise SystemExit("canonical compact/zero-fetch proof is incomplete")
    if proof.get("installed_hash") != proof["source_hashes"]["safe"]:
        raise SystemExit("canonical installed hash does not match safe source hash")
    readiness.update({
        "phase": "CANONICAL_STUDIONET_RELEASE",
        "status": "CANONICAL_DEPLOYED",
        "canonical_deployment": "CANONICAL_DEPLOYED",
        "result": "PASS",
        "git_sha": head,
        "source_revision": proof["source_revision"],
        "qualification_head": proof["qualification_head"],
        "canonical_deployment_artifact_head": proof["canonical_deployment_artifact_head"],
        "source_manifest_sha256": proof["source_manifest_sha256"],
        "fee_profile_sha256": proof["fee_profile_sha256"],
        "network": {
            "name": "Studionet", "rpc": "https://studio.genlayer.com/api",
            "chain_id": 61999, "profile_only": False,
        },
        "canonical": {
            "governor": proof["governor"],
            "target": proof["target"],
            "proposal_id": proof["proposal_id"],
            "proposal_state": proof["final_proposal_state"],
            "installed_hash": proof["installed_hash"],
            "persistent_state_preserved": proof["persistent_state_preserved"],
            "value_nonce_preserved": proof["value_nonce_preserved"],
            "upgrade_authority_preserved": proof["upgrade_authority_preserved"],
            "safe_feature_verified": proof["safe_feature_verified"],
            "review_decision": proof["decision"],
            "review_vector": proof["semantic_vector"],
            "review_web_fetches": proof["review_web_fetches"],
            "compact_result_size": proof["compact_result_size"],
            "snapshot_digest": proof["snapshot_digest"],
            "live_proof_path": str(PROOF.relative_to(ROOT)).replace("\\", "/"),
            "manifest_path": str(MANIFEST.relative_to(ROOT)).replace("\\", "/"),
        },
        "provenance": {
            "PROFILED_NON_CANONICAL": {
                "governor": readiness.get("safe_profile", {}).get("governor"),
                "target": readiness.get("safe_profile", {}).get("target"),
            },
            "QUALIFIED": proof["qualification_head"],
            "CANONICAL_DEPLOYED": head,
            "source_revision": proof["source_revision"],
        },
    })
    readiness.setdefault("gates", {})["canonical_live_proof"] = "PASS"
    readiness["gates"]["canonical_safe_verified"] = "PASS"
    readiness["gates"]["canonical_unsafe_reference"] = "PASS"
    readiness["fee_profile"] = {
        "path": "deployments/studionet/v2.3/fee-profile.json",
        "coverage_path": "artifacts/studionet/v2.3/fee-profile-coverage.json",
        "sha256": proof["fee_profile_sha256"],
    }
    readiness["canonical_manifest"] = {
        "path": str(MANIFEST.relative_to(ROOT)).replace("\\", "/"),
        "sha256": _sha(MANIFEST),
        "result": "PASS",
    }
    # Keep the qualified disposable proof intact and explicitly mark the
    # canonical path as separate from both historical profile environments.
    readiness["profile_addresses_remain_non_canonical"] = True
    READINESS.write_text(json.dumps(readiness, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"readiness": str(READINESS), "head": head, "result": "PASS"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
