"""Build a deterministic evidence envelope from explicitly supplied values.

This utility never invents timestamps, hashes, transaction identifiers, or
review results. It serializes supplied CI/security attestations; publication,
authentication, and immutable-URL checks remain governance responsibilities.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def sha256(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{64}", value) is not None


def evidence_id(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,159}", value) is not None


def strict_bool(value: str) -> bool:
    if value.lower() not in ("true", "false"):
        raise argparse.ArgumentTypeError("expected true or false")
    return value.lower() == "true"


def make_envelope(args: argparse.Namespace) -> dict[str, object]:
    for label, value in (("target", args.target), ("issuer", args.issuer),
                         ("policy_fingerprint", args.policy_fingerprint)):
        if not value:
            raise ValueError(f"{label} is required")
    for label, value in (("parent_sha256", args.parent_sha256),
                         ("candidate_sha256", args.candidate_sha256)):
        if not sha256(value):
            raise ValueError(f"{label} must be lowercase SHA-256")
    if not evidence_id(args.evidence_id):
        raise ValueError("evidence_id is malformed")
    if args.published_at >= args.expires_at:
        raise ValueError("published_at must be earlier than expires_at")
    envelope: dict[str, object] = {
        "schema": "sentinelx-evidence-v1",
        "kind": args.kind,
        "evidence_id": args.evidence_id,
        "issuer": args.issuer,
        "target": args.target,
        "parent_sha256": args.parent_sha256,
        "candidate_sha256": args.candidate_sha256,
        "policy_fingerprint": args.policy_fingerprint,
        "published_at": args.published_at,
        "expires_at": args.expires_at,
    }
    if args.kind == "ci":
        if args.checks_json is None:
            raise ValueError("CI evidence requires --checks-json")
        checks = json.loads(args.checks_json)
        if (not isinstance(checks, dict)
                or set(checks) != set(("genvm_lint", "typecheck", "schema",
                                       "direct_tests", "adversarial_tests",
                                       "source_parity", "transaction_safety"))
                or any(type(value) is not bool for value in checks.values())):
            raise ValueError("CI checks must contain exactly the seven boolean gates")
        envelope["checks"] = checks
    else:
        if args.verdict is None or args.independent_review is None:
            raise ValueError("security evidence requires --verdict and --independent-review")
        if args.verdict != "PASS" or args.independent_review is not True:
            raise ValueError("security evidence can be emitted only for PASS with independent_review=true")
        envelope["verdict"] = args.verdict
        envelope["independent_review"] = args.independent_review
    return envelope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("ci", "security"), required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--evidence-id", required=True)
    parser.add_argument("--parent-sha256", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--policy-fingerprint", required=True)
    parser.add_argument("--published-at", type=int, required=True)
    parser.add_argument("--expires-at", type=int, required=True)
    parser.add_argument("--checks-json")
    parser.add_argument("--verdict")
    parser.add_argument("--independent-review", type=strict_bool)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        envelope = make_envelope(args)
        rendered = json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n"
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8", newline="\n")
        else:
            print(rendered, end="")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
