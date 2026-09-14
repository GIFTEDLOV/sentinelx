"""Generate a measured Studio-dev v0.6 fee profile when writes are authorized.

This command is fail-closed.  ``--dry-run`` prints the exact gltest command;
``--run`` refuses to run without an explicit write gate and validates that the
result contains finalized observations for every required operation.  An
empty profile is never checked in as if it were a measurement.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RPC = "https://studio-dev.genlayer.com/api"
NETWORK = "studio_devnet"
CHAIN_ID = 61997
HEADROOM = 1.25
PROFILE = ROOT / "fee-profile.json"
REQUIRED_METHODS = (
    "register_with_sentinelx",
    "create_proposal",
    "review_proposal",
    "install_reviewed_upgrade",
    "confirm_install",
    "reconcile_install",
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
    missing = [method for method in REQUIRED_METHODS if not isinstance(methods.get(method), dict)]
    if missing:
        raise ValueError("missing measured operations: " + ", ".join(missing))
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--allow-network-writes", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print(" ".join(command()))
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
