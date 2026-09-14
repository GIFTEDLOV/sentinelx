"""Generate a SentinelX CI evidence envelope from explicit, reproducible inputs.

The generator computes hashes from bytes on disk, rejects mutable or unsafe
source URLs, runs the deterministic gates, and writes output only after every
required CI boolean is true.  It never signs, publishes, or creates security
evidence.  Timestamps, authorities, target, policy fingerprint, and evidence
ID must all be supplied by the caller; there are no demo defaults.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from argparse import Namespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REQUIRED_CHECKS = (
    "genvm_lint",
    "typecheck",
    "schema",
    "direct_tests",
    "adversarial_tests",
    "source_parity",
    "transaction_safety",
)
RAW_BASE = "https://raw.githubusercontent.com/"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def commit_from_url(url: str, prefix: str) -> str:
    from direct.sentinelx_model import immutable_url

    if not immutable_url(url, prefix):
        raise ValueError(f"not an immutable raw GitHub URL under its prefix: {url}")
    return url[len(prefix) :].split("/", 1)[0]


def _required_text(name: str, value: str) -> str:
    if not value or value.startswith("<<") or value.endswith(">>"):
        raise ValueError(f"{name} must be supplied and cannot be a placeholder")
    if not value.isascii():
        raise ValueError(f"{name} must be ASCII")
    return value


def _run(command: list[str]) -> bool:
    environment = os.environ.copy()
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["GENVM_VERSION"] = "v0.6.0-rc3"
    completed = subprocess.run(
        command, cwd=ROOT, env=environment, check=False,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace",
    )
    return completed.returncode == 0


def run_deterministic_gates() -> dict[str, bool]:
    """Run the gates that are available to a public CI checkout."""
    preflight = _run([sys.executable, "scripts/preflight.py"])
    direct_tests = _run([sys.executable, "-m", "pytest", "tests/direct", "-q", "--tb=short"])
    typecheck = _run([sys.executable, "scripts/typecheck_contracts.py"])
    all_local = preflight and direct_tests and typecheck
    return {
        "genvm_lint": preflight,
        "typecheck": typecheck,
        "schema": preflight,
        "direct_tests": direct_tests,
        "adversarial_tests": direct_tests,
        "source_parity": False,
        "transaction_safety": all_local,
    }


def make_ci_evidence(
    *,
    target: str,
    issuer: str,
    evidence_id: str,
    parent: Path,
    candidate: Path,
    parent_source_url: str,
    candidate_source_url: str,
    source_prefix: str,
    ci_prefix: str,
    policy_fingerprint: str,
    published_at: int,
    expires_at: int,
    run_checks: bool = True,
) -> dict[str, object]:
    from direct.sentinelx_model import is_sha256, raw_owner

    target = _required_text("target", target)
    issuer = _required_text("issuer", issuer)
    evidence_id = _required_text("evidence_id", evidence_id)
    policy_fingerprint = _required_text("policy_fingerprint", policy_fingerprint)
    if not is_sha256(policy_fingerprint):
        raise ValueError("policy_fingerprint must be lowercase SHA-256")
    if not raw_owner(source_prefix) or not raw_owner(ci_prefix):
        raise ValueError("source and CI prefixes must be canonical raw GitHub prefixes")
    if source_prefix == ci_prefix:
        raise ValueError("source and CI prefixes must be distinct")
    parent_commit = commit_from_url(parent_source_url, source_prefix)
    candidate_commit = commit_from_url(candidate_source_url, source_prefix)
    if parent_commit == candidate_commit:
        raise ValueError("parent and candidate must use different immutable commits")
    if not parent.is_file() or not candidate.is_file():
        raise ValueError("parent and candidate files must exist")
    parent_hash = sha256_file(parent)
    candidate_hash = sha256_file(candidate)
    if parent_hash == candidate_hash:
        raise ValueError("candidate bytes must differ from parent bytes")
    checks = run_deterministic_gates() if run_checks else {name: False for name in REQUIRED_CHECKS}
    # The exact immutable source URLs plus byte hashes prove checkout parity;
    # this is deliberately local-source parity, not a claim about deployment.
    checks["source_parity"] = True
    if set(checks) != set(REQUIRED_CHECKS) or any(value is not True for value in checks.values()):
        raise ValueError("all seven deterministic CI checks must be true")
    args = Namespace(
        target=target,
        issuer=issuer,
        policy_fingerprint=policy_fingerprint,
        parent_sha256=parent_hash,
        candidate_sha256=candidate_hash,
        evidence_id=evidence_id,
        published_at=published_at,
        expires_at=expires_at,
        kind="ci",
        checks_json=json.dumps(checks, sort_keys=True),
        verdict=None,
        independent_review=None,
    )
    from scripts.build_evidence import make_envelope

    return make_envelope(args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--parent-source-url", required=True)
    parser.add_argument("--candidate-source-url", required=True)
    parser.add_argument("--source-prefix", required=True)
    parser.add_argument("--ci-prefix", required=True)
    parser.add_argument("--policy-fingerprint", required=True)
    parser.add_argument("--published-at", type=int, required=True)
    parser.add_argument("--expires-at", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        envelope = make_ci_evidence(**vars(args))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(envelope, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
