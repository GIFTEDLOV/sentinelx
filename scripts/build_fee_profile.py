"""Generate a measured Studio-dev v0.6 fee profile when writes are authorized.

This command is fail-closed.  ``--dry-run`` prints the exact gltest command;
``--run`` refuses to run without an explicit write gate and validates that the
result contains finalized observations. ``--from-journal`` consumes only
finalized, successful observations from the disposable SDK profiling journal.
Partial coverage is honest and is recorded separately; an empty profile is
never checked in as if it were a measurement.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RPC = "https://studio-dev.genlayer.com/api"
NETWORK = "studio_devnet"
CHAIN_ID = 61997
HEADROOM = 1.25
PROFILE = ROOT / "fee-profile.json"
REQUESTED_METHODS = (
    "register_with_sentinelx",
    "register_target",
    "create_proposal",
    "review_proposal",
    "repair_evidence",
    "retry_review",
    "cancel_proposal",
    "expire_proposal",
    "reconcile_install",
    "mark_execution_timeout",
    "confirm_install",
    "install_reviewed_upgrade",
)


def command() -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        "tests/integration",
        "--fee-profile",
        str(PROFILE),
        "--fee-profile-headroom",
        str(HEADROOM),
        "--rpc-url",
        RPC,
        "--network",
        NETWORK,
        "--chain-type",
        NETWORK,
    ]


def validate_profile(path: Path) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read generated fee profile: {error}") from error
    if not isinstance(document, dict):
        raise ValueError("fee profile must be a JSON object")
    if document.get("version") != 1 or document.get("network") != NETWORK:
        raise ValueError("fee profile has an unexpected version or network")
    if document.get("chainId") != CHAIN_ID:
        raise ValueError("fee profile chainId is not 61997")
    deploy = document.get("deploy")
    methods = document.get("methods")
    if not isinstance(deploy, dict) or not deploy:
        raise ValueError("deploy observation is missing; no measured profile created")
    if not isinstance(methods, dict):
        raise ValueError("method observations are missing")
    if not methods:
        raise ValueError("no method observations; no measured profile created")
    return document


def _journal_observations(path: Path) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read profiling journal: {error}") from error
    if not isinstance(document, dict) or not isinstance(document.get("operations"), dict):
        raise ValueError("profiling journal schema is invalid")

    receipts: list[dict[str, Any]] = []
    observed_deploys: list[str] = []
    observed_methods: list[str] = []
    for operation, record in document["operations"].items():
        if not isinstance(record, dict):
            continue
        lifecycle = record.get("lifecycle")
        execution = record.get("execution_result")
        receipt = record.get("receipt")
        if (record.get("state") != "FINALIZED_EXECUTED"
                or not isinstance(lifecycle, dict)
                or lifecycle.get("stored_status") != "Finalized"
                or execution != "FINISHED_WITH_RETURN"
                or not isinstance(receipt, dict)):
            continue
        kind = record.get("fee_observation_kind")
        if kind == "deploy":
            observed_deploys.append(str(record.get("contract_name") or operation))
        elif kind == "method":
            method = record.get("method")
            if not isinstance(method, str) or not method:
                raise ValueError(f"method observation {operation} has no method name")
            observed_methods.append(method)
        else:
            continue
        receipts.append({"kind": kind, "method": record.get("method"), "receipt": receipt})
    if not receipts:
        raise ValueError("journal has no finalized FINISHED_WITH_RETURN fee observations")
    return receipts, sorted(set(observed_deploys)), sorted(set(observed_methods))


def build_profile_from_journal(
    journal_path: Path, profile_path: Path, *, preserve_existing: bool = False
) -> dict[str, object]:
    from gltest.fees.profile import FeeProfileCollector

    observations, observed_deploys, observed_methods = _journal_observations(journal_path)
    collector = FeeProfileCollector()
    for item in observations:
        if item["kind"] == "deploy":
            collector.record_deploy(item["receipt"])
        else:
            collector.record_method(str(item["method"]), item["receipt"])
    if profile_path.exists() and preserve_existing:
        profile = validate_profile(profile_path)
    else:
        profile = collector.write(profile_path, network=NETWORK, headroom=HEADROOM, chain_id=CHAIN_ID)
    validate_profile(profile_path)

    missing_methods = [method for method in REQUESTED_METHODS if method not in observed_methods]
    coverage = {
        "schema": "sentinelx-fee-profile-coverage-v1",
        "network": NETWORK,
        "rpc": RPC,
        "chainId": CHAIN_ID,
        "headroom": HEADROOM,
        "profilePath": str(profile_path.relative_to(ROOT)).replace("\\", "/"),
        "observed": {"deploy": observed_deploys, "methods": observed_methods},
        "missing": {"deploy": ["sentinelx_governor", "protected_app_v1"] if not observed_deploys else [],
                    "methods": missing_methods},
        "sourceJournal": str(journal_path.relative_to(ROOT)).replace("\\", "/"),
        "finalizedOnly": True,
        "acceptedOnlyExcluded": True,
    }
    coverage_path = ROOT / "artifacts" / "fee-profile-coverage.json"
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--from-journal", type=Path)
    parser.add_argument("--allow-network-writes", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print(" ".join(command()))
        return 0
    if args.from_journal is not None:
        profile_preexisting = PROFILE.exists()
        try:
            profile = build_profile_from_journal(
                args.from_journal.resolve(), PROFILE, preserve_existing=PROFILE.exists()
            )
        except (OSError, ValueError, ImportError) as error:
            if not profile_preexisting:
                PROFILE.unlink(missing_ok=True)
            parser.error(str(error))
        methods = profile.get("methods")
        observed_methods = sorted(methods.keys()) if isinstance(methods, dict) else []
        print(json.dumps({"profile": str(PROFILE), "coverage": str(ROOT / "artifacts" / "fee-profile-coverage.json"), "observed_methods": observed_methods}, indent=2))
        return 0
    if not args.allow_network_writes or os.environ.get("SENTINELX_ALLOW_BROADCAST") != "1":
        parser.error("--run requires --allow-network-writes and SENTINELX_ALLOW_BROADCAST=1")
    if PROFILE.exists():
        parser.error(f"refusing to overwrite existing {PROFILE}; move it aside after review")
    result = subprocess.run(command(), cwd=ROOT, check=False)
    if result.returncode != 0:
        PROFILE.unlink(missing_ok=True)
        return result.returncode
    try:
        validate_profile(PROFILE)
    except ValueError as error:
        PROFILE.unlink(missing_ok=True)
        parser.error(str(error))
    print(f"validated measured profile: {PROFILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
