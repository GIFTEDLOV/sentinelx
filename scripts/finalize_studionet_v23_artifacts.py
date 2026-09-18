"""Regenerate V2.3 Studionet artifacts from a completed profile journal.

This is read-only with respect to Studionet.  It reuses only terminal journal
observations and is intended for tooling interruptions after qualification.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SENTINELX_PROFILE_STATE", "studionet-v23-profile-r1")
os.environ.setdefault("SENTINELX_STUDIONET_PROFILE_STATE", "studionet-v23-profile-r1")

from scripts import studionet_stable_bridge as bridge  # noqa: E402
from scripts import studionet_stable_profile as profile  # noqa: E402


def _address_key(value: object) -> str:
    text = str(value).strip().lower()
    if text.startswith("addr#"):
        text = text[5:]
    if text.startswith("0x"):
        text = text[2:]
    return text


def main() -> int:
    run_path = bridge.JOURNAL_PATH.parent / "run.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    final_target = run.get("final_target_state") or {}
    run["upgrade_authority_preserved"] = (
        _address_key(final_target.get("governor")) == _address_key(run.get("governor"))
    )
    run_path.write_text(json.dumps(run, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if isinstance(run.get("source_revision"), str) and run["source_revision"]:
        profile.SOURCE_REVISION = run["source_revision"]
    readback_path = ROOT / "artifacts" / "studionet" / "v2.3" / "live-state-readback.json"
    if readback_path.exists():
        readback = json.loads(readback_path.read_text(encoding="utf-8"))
        unsafe_proposal = readback.get("unsafe_proposal") or {}
        unsafe_vector = unsafe_proposal.get("semantic_vector")
        if isinstance(unsafe_vector, dict):
            run["unsafe_semantic_vector"] = unsafe_vector
            run["unsafe_false_vector_fields"] = sorted(
                key for key, value in unsafe_vector.items() if value is False
            )

    journal_obj = bridge.journal()
    outputs = profile._write_profile_outputs(
        run=run,
        journal_obj=journal_obj,
        preflight={"fee_policy": run.get("fee_policy", {})},
        initial_fee_estimate=run.get("initial_deploy_fee_estimate", {}),
    )
    readiness_path = profile.READINESS
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    readiness["git_sha"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    readiness_path.write_text(
        json.dumps(readiness, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({
        "fee_profile_sha256": outputs["fee_profile_sha256"],
        "fee_profile": str(profile.FEE_PROFILE),
        "coverage": str(profile.COVERAGE),
        "readiness": str(profile.READINESS),
        "upgrade_authority_preserved": run["upgrade_authority_preserved"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
