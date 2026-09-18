"""Fail-closed repository integrity checks for the canonical Studionet release."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "governor": "1c53c221300a5fd4e901a3608c72f87c88ed14136f5a95f786a2854355270423",
    "target": "47bf21c12574ec8d43a41d79c987e1206b3c65b3e7f0e7998c8a3ff1179d2631",
    "safe": "1073b34f141b9dc5ba689ef3d98293fd628e30695dbd9092a9c6ecaba3d8c27d",
    "unsafe": "380c80e653a2d87e02648eec57dbfd46f898fb1a4cccfbe349c027ffa9149340",
}
PATHS = {
    "governor": ROOT / "contracts" / "sentinelx_governor.py",
    "target": ROOT / "contracts" / "protected_app_v1.py",
    "safe": ROOT / "contracts" / "protected_app_v2_safe.py",
    "unsafe": ROOT / "contracts" / "protected_app_v2_unsafe.py",
}
CANONICAL_GOVERNOR = "0xb28b8E7F8930b4bd7Ed8572dA7e51AA4ca9D7cA8"
CANONICAL_TARGET = "0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21"
RPC = "https://studio.genlayer.com/api"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a JSON object")
    return value


def run() -> dict[str, object]:
    errors: list[str] = []
    actual = {name: sha(path) for name, path in PATHS.items()}
    for name, expected in EXPECTED.items():
        if actual[name] != expected:
            errors.append(f"{name} source hash changed: {actual[name]}")

    source_manifest_path = ROOT / "deployments" / "studionet" / "v2.3" / "SOURCE_MANIFEST.json"
    readiness_path = ROOT / "deployments" / "studionet" / "v2.3" / "DEPLOYMENT_READINESS.json"
    canonical_path = ROOT / "deployments" / "studionet" / "v2.3" / "CANONICAL_DEPLOYMENT.json"
    source_manifest = load(source_manifest_path)
    readiness = load(readiness_path)
    canonical = load(canonical_path)
    if source_manifest.get("network") != "studionet" or source_manifest.get("chain_id") != 61999 or source_manifest.get("rpc") != RPC:
        errors.append("source manifest network binding is not canonical Studionet")
    if source_manifest.get("canonical_deployment_attempted") is not True or source_manifest.get("canonical_governor") != CANONICAL_GOVERNOR or source_manifest.get("canonical_target") != CANONICAL_TARGET:
        errors.append("source manifest does not record the canonical deployment")
    if readiness.get("result") != "PASS" or readiness.get("status") != "CANONICAL_DEPLOYED":
        errors.append("readiness manifest is not a passing canonical release")
    if canonical.get("result") != "PASS" or canonical.get("final_proposal_state") != "VERIFIED":
        errors.append("canonical deployment manifest is not a passing VERIFIED release")
    for document_name, document in (("readiness", readiness), ("canonical", canonical)):
        nested_canonical = document.get("canonical") if isinstance(document.get("canonical"), dict) else {}
        if document.get("canonical_governor", nested_canonical.get("governor")) != CANONICAL_GOVERNOR:
            errors.append(f"{document_name} governor binding is wrong")
        if document.get("canonical_target", nested_canonical.get("target")) != CANONICAL_TARGET:
            errors.append(f"{document_name} target binding is wrong")
        nested_network = document.get("network") if isinstance(document.get("network"), dict) else {}
        if document.get("chain_id", nested_network.get("chain_id")) != 61999:
            errors.append(f"{document_name} chain binding is wrong")
    vector = canonical.get("semantic_vector")
    if not isinstance(vector, dict) or len(vector) != 14 or not all(value is True for value in vector.values()):
        errors.append("canonical semantic vector is not exactly fourteen true fields")
    if canonical.get("review_web_fetch_count") != 0:
        errors.append("canonical review is not zero-fetch")

    frontend_chain = (ROOT / "frontend" / "lib" / "genlayer" / "chains.ts").read_text(encoding="utf-8")
    for required in ("STUDIONET_RPC = \"https://studio.genlayer.com/api\"", "STUDIONET_CHAIN_ID = 61999", CANONICAL_GOVERNOR, CANONICAL_TARGET):
        if required not in frontend_chain:
            errors.append(f"frontend canonical configuration missing: {required}")
    active_frontend = [*ROOT.glob("frontend/app/**/*.tsx"), *ROOT.glob("frontend/components/**/*.tsx"), *ROOT.glob("frontend/lib/genlayer/**/*.ts")]
    for path in active_frontend:
        text = path.read_text(encoding="utf-8")
        if "studio-dev.genlayer.com" in text or "61997" in text:
            errors.append(f"historical Studio-dev setting appears in active frontend file: {path.relative_to(ROOT)}")

    if errors:
        raise RuntimeError("; ".join(errors))
    return {
        "schema": "sentinelx-release-integrity-v1",
        "result": "PASS",
        "network": "Studionet",
        "chain_id": 61999,
        "rpc": RPC,
        "source_hashes": actual,
        "canonical_governor": CANONICAL_GOVERNOR,
        "canonical_target": CANONICAL_TARGET,
        "review_web_fetch_count": 0,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
