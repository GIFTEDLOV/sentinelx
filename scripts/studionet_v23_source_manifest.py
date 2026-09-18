"""Build and validate the SentinelX V2.3 Studionet source manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "deployments" / "studionet" / "v2.3" / "SOURCE_MANIFEST.json"
SOURCES = {
    "governor": ROOT / "contracts" / "sentinelx_governor.py",
    "target": ROOT / "contracts" / "protected_app_v1.py",
    "safe": ROOT / "contracts" / "protected_app_v2_safe.py",
    "unsafe": ROOT / "contracts" / "protected_app_v2_unsafe.py",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(*, source_commit: str | None = None) -> dict[str, object]:
    return {
        "schema": "sentinelx-studionet-v23-source-manifest-v1",
        "release": "SentinelX V2.3 Studionet Stable",
        "git_commit": source_commit or subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "network": "studionet",
        "rpc": "https://studio.genlayer.com/api",
        "chain_id": 61999,
        "sources": {
            name: {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(path),
                "bytes": len(path.read_bytes()),
            }
            for name, path in SOURCES.items()
        },
        "toolchain": {
            "genlayer_js": "1.1.8",
            "genlayer_py": "0.18.0",
            "genlayer_test": "0.29.2",
            "genvm_linter": "0.11.0",
            "genvm_runner": "v0.2.12",
            "py_genlayer_dependency": {
                "runner": "1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6",
                "stdlib": "11rhn002yfajawsz7fai6mykznbxkxs6l91iskj5cm82c92qhy3v",
            },
        },
        "historical_revisions_preserved": ["V2", "V2.1", "V2.2 Studionet Stable", "V2.2 Studio-dev"],
        "canonical_deployment_attempted": False,
    }


def validate_manifest(document: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if document.get("network") != "studionet":
        errors.append("network is not studionet")
    if document.get("rpc") != "https://studio.genlayer.com/api":
        errors.append("rpc is not the locked Studionet endpoint")
    if document.get("chain_id") != 61999:
        errors.append("chain_id is not 61999")
    sources = document.get("sources")
    if not isinstance(sources, dict):
        return [*errors, "sources is not an object"]
    for name, path in SOURCES.items():
        entry = sources.get(name)
        if not isinstance(entry, dict):
            errors.append(f"missing source entry: {name}")
            continue
        if entry.get("sha256") != sha256(path):
            errors.append(f"source hash mismatch: {name}")
        if entry.get("bytes") != len(path.read_bytes()):
            errors.append(f"source byte count mismatch: {name}")
    return errors


def write_manifest(*, source_commit: str | None = None) -> Path:
    document = build_manifest(source_commit=source_commit)
    errors = validate_manifest(document)
    if errors:
        raise RuntimeError("; ".join(errors))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return OUTPUT


def verify_manifest(path: Path = OUTPUT) -> list[str]:
    if not path.exists():
        return [f"missing manifest: {path}"]
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"manifest unreadable: {error}"]
    if not isinstance(document, dict):
        return ["manifest is not a JSON object"]
    return validate_manifest(document)


if __name__ == "__main__":
    path = write_manifest()
    print(json.dumps({"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(path)}, sort_keys=True))
