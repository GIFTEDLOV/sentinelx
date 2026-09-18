"""Fail-closed, read-only preflight for stable Studionet writes."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
RPC = "https://studio.genlayer.com/api"
CHAIN_ID = 61999
JOURNAL = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "SentinelX" / "studionet-v23-profile-r1" / "transactions.json"
OUTPUT = ROOT / "artifacts" / "studionet" / "v2.3" / "preflight-pass.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    errors: list[str] = []
    from genlayer_py.chains import studionet

    if studionet.id != CHAIN_ID:
        errors.append("installed stable Studionet preset has the wrong chain ID")
    if studionet.rpc_urls["default"]["http"][0] != RPC:
        errors.append("installed stable Studionet preset has the wrong RPC")
    config = (ROOT / "gltest.config.yaml").read_text(encoding="utf-8")
    if "default: studionet" not in config or "studio_devnet" in config or "61997" in config:
        errors.append("gltest config is not stable Studionet-only")
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    if package.get("dependencies", {}).get("genlayer-js") != "1.1.8":
        errors.append("frontend does not pin genlayer-js 1.1.8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for required in ("genlayer-py==0.18.0", "genlayer-test==0.29.2"):
        if required not in requirements:
            errors.append(f"missing stable dependency pin: {required}")
    from scripts.studionet_v23_source_manifest import verify_manifest
    errors.extend(verify_manifest())
    unresolved: list[str] = []
    if JOURNAL.exists():
        document = json.loads(JOURNAL.read_text(encoding="utf-8"))
        for name, record in document.get("operations", {}).items():
            if isinstance(record, dict) and record.get("state") not in {
                "FINALIZED_EXECUTED", "FINALIZED_EXECUTION_FAILED", "BROADCAST_CALL_RAISED", "BLOCKED_BEFORE_BROADCAST",
            }:
                unresolved.append(str(name))
    if unresolved:
        errors.append("unresolved stable journal operations: " + ", ".join(unresolved))
    if errors:
        raise SystemExit("STUDIONET_PREFLIGHT_FAIL: " + "; ".join(errors))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": "sentinelx-studionet-preflight-v1",
        "result": "PASS",
        "network": "Studionet",
        "rpc": RPC,
        "chain_id": CHAIN_ID,
        "source_manifest_sha256": _sha(ROOT / "deployments" / "studionet" / "v2.3" / "SOURCE_MANIFEST.json"),
        "unresolved_journal_operations": [],
        "canonical_deployment_attempted": True,
        "canonical_deployment_status": "CANONICAL_DEPLOYED",
        "canonical_governor": "0xb28b8E7F8930b4bd7Ed8572dA7e51AA4ca9D7cA8",
        "canonical_target": "0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21",
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
