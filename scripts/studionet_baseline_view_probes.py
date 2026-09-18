"""Run the missing three-mode probe against a fresh, never-upgraded target."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import studionet_finalized_view_probes as probes  # noqa: E402


BASELINE_TARGET = "0xd05C4bca23E1d94324ff7dD2ab343924b7262efA"
OUTPUT = ROOT / "artifacts" / "studionet" / "fresh-baseline-view-probe-results.json"


def main() -> int:
    client = probes.bridge.make_client()
    journal_obj = probes.bridge.journal()
    preflight = probes.bridge.account_preflight(client, probes.bridge.EXPECTED_DEPLOYER, journal_obj)
    if preflight["latest_nonce"] != preflight["pending_nonce"]:
        raise RuntimeError("latest and pending nonce differ before baseline diagnostic writes")
    if preflight["unresolved_journal_operations"]:
        raise RuntimeError("unresolved baseline diagnostic journal operations exist")

    caller, deployment = probes._deploy(
        client=client,
        journal_obj=journal_obj,
        operation="baseline_probe.deploy_caller",
        source=probes.SENTINELX_CALLER_SOURCE,
        args=[],
        name="SentinelXViewProbeCaller baseline diagnostic",
    )
    result = {
        "schema": "sentinelx-studionet-fresh-baseline-view-probe-v1",
        "diagnostic_only": True,
        "network": probes.NETWORK,
        "rpc": probes.RPC,
        "chain_id": probes.CHAIN_ID,
        "target": BASELINE_TARGET,
        "caller": caller,
        "caller_deployment": deployment,
        "external_installed_proposal_id": probes.bridge.read(client, BASELINE_TARGET, "get_installed_proposal_id"),
        "external_installed_candidate_hash": probes.bridge.read(client, BASELINE_TARGET, "get_installed_candidate_hash"),
        "default": probes._attempt(
            client=client, journal_obj=journal_obj, operation="baseline_probe.default",
            method="probe_default_installed", address=caller, args=[BASELINE_TARGET],
            readback=(caller, "get_last_installed", []),
        ),
        "latest_finalized": probes._attempt(
            client=client, journal_obj=journal_obj, operation="baseline_probe.latest_finalized",
            method="probe_finalized_installed", address=caller, args=[BASELINE_TARGET],
            readback=(caller, "get_last_installed", []),
        ),
        "latest_decided": probes._attempt(
            client=client, journal_obj=journal_obj, operation="baseline_probe.latest_decided",
            method="probe_decided_installed", address=caller, args=[BASELINE_TARGET],
            readback=(caller, "get_last_installed", []),
        ),
        "journal_path": str(probes.bridge.JOURNAL_PATH),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
