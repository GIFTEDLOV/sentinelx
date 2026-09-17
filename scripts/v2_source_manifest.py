"""Build and verify the frozen SentinelX V2.2 source manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "deployments" / "v2.2" / "SOURCE_MANIFEST.json"
CONTRACT_PATHS = (
    "contracts/sentinelx_governor.py",
    "contracts/protected_app_v1.py",
    "contracts/protected_app_v2_safe.py",
    "contracts/protected_app_v2_unsafe.py",
)


def _source_record(relative_path: str) -> dict[str, Any]:
    path = ROOT / relative_path
    data = path.read_bytes()
    return {
        "path": relative_path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def build_manifest() -> dict[str, Any]:
    return {
        "schema": "sentinelx-v2.2-source-manifest-v1",
        "contract_version": "SentinelX V2.2",
        "source_lineage": "SentinelX V2 failed disposable registration profile -> V2.1 corrected registration state machine -> V2.1 capture-output-limit profile -> V2.2 deterministic byte staging and compact remote attestation",
        "network": "studio-dev",
        "rpc": "https://studio-dev.genlayer.com/api",
        "chain_id": 61997,
        "toolchain": {
            "genlayer_cli": "0.40.0-rc.3",
            "genlayer_js": "2.0.0-rc.1",
            "genlayer_py": "0.19.0rc2",
            "gltest": "0.30.0rc2",
            "genvm_runner": "v0.6.0-rc5",
            "genvm_linter_static": "0.11.0",
            "genvm_linter_semantic": "0.11.1rc2",
        },
        "contracts": [_source_record(path) for path in CONTRACT_PATHS],
    }


def verify_manifest(manifest: dict[str, Any] | None = None) -> list[str]:
    value = manifest if manifest is not None else json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []
    if value.get("schema") != "sentinelx-v2.2-source-manifest-v1":
        errors.append("manifest schema mismatch")
    if value.get("network") != "studio-dev" or value.get("chain_id") != 61997:
        errors.append("manifest network mismatch")
    records = value.get("contracts")
    if not isinstance(records, list) or [record.get("path") for record in records] != list(CONTRACT_PATHS):
        errors.append("manifest contract path list mismatch")
        return errors
    for record in records:
        path = ROOT / str(record["path"])
        if not path.is_file():
            errors.append(f"missing source: {record['path']}")
            continue
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != record.get("sha256"):
            errors.append(f"source hash mismatch: {record['path']}")
        if len(data) != record.get("bytes"):
            errors.append(f"source byte count mismatch: {record['path']}")
    return errors


if __name__ == "__main__":
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest()
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))
