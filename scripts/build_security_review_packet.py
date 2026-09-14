"""Assemble a review packet for a genuinely independent security publisher.

This command copies exact parent/candidate bytes, computes their hashes, and
renders a deterministic textual diff and the required SentinelX security
evidence schema.  It does not choose a reviewer, issue a verdict, create an
evidence ID, or publish anything.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _required(value: str, label: str) -> str:
    if not value or value.startswith("<<") or value.endswith(">>"):
        raise ValueError(f"{label} must be supplied")
    return value


def build_packet(
    *,
    parent: Path,
    candidate: Path,
    constitution_file: Path,
    release_intent: str,
    output_dir: Path,
    target: str = "<<TARGET_ADDRESS>>",
    policy_fingerprint: str = "<<POLICY_FINGERPRINT>>",
    parent_source_url: str = "<<PARENT_SOURCE_URL>>",
    candidate_source_url: str = "<<CANDIDATE_SOURCE_URL>>",
    force: bool = False,
) -> dict[str, object]:
    release_intent = _required(release_intent, "release_intent")
    if not parent.is_file() or not candidate.is_file() or not constitution_file.is_file():
        raise ValueError("parent, candidate, and constitution files must exist")
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        raise ValueError("output directory is not empty; use --force only after review")
    try:
        constitution = json.loads(constitution_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"constitution is not valid UTF-8 JSON: {error}") from error
    if not isinstance(constitution, dict):
        raise ValueError("constitution must be a JSON object")
    parent_bytes = parent.read_bytes()
    candidate_bytes = candidate.read_bytes()
    try:
        parent_text = parent_bytes.decode("utf-8").splitlines(keepends=True)
        candidate_text = candidate_bytes.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError as error:
        raise ValueError("source files must be UTF-8 for semantic diff generation") from error
    parent_hash = hashlib.sha256(parent_bytes).hexdigest()
    candidate_hash = hashlib.sha256(candidate_bytes).hexdigest()
    schema: dict[str, object] = {
        "schema": "sentinelx-evidence-v1",
        "kind": "security",
        "evidence_id": "<<UNIQUE_SECURITY_EVIDENCE_ID>>",
        "issuer": "<<INDEPENDENT_SECURITY_AUTHORITY>>",
        "target": target,
        "parent_sha256": parent_hash,
        "candidate_sha256": candidate_hash,
        "policy_fingerprint": policy_fingerprint,
        "published_at": "<<PUBLISHED_AT_UNIX_SECONDS>>",
        "expires_at": "<<EXPIRES_AT_UNIX_SECONDS>>",
        "verdict": "PASS",
        "independent_review": True,
    }
    packet: dict[str, object] = {
        "schema": "sentinelx-security-review-packet-v1",
        "publishable": False,
        "target": target,
        "policy_fingerprint": policy_fingerprint,
        "parent_source_url": parent_source_url,
        "candidate_source_url": candidate_source_url,
        "parent_sha256": parent_hash,
        "candidate_sha256": candidate_hash,
        "release_constitution": constitution,
        "release_intent": release_intent,
        "required_evidence_schema": schema,
        "reviewer_instructions": [
            "Independently retrieve both immutable source URLs.",
            "Recompute both SHA-256 values from retrieved bytes.",
            "Evaluate all fourteen SentinelX semantic safety fields.",
            "Set independent_review true only when publisher independence is real.",
            "Publish the exact envelope at an immutable commit only after review.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "parent.py").write_bytes(parent_bytes)
    (output_dir / "candidate.py").write_bytes(candidate_bytes)
    (output_dir / "semantic.diff").write_text(
        "".join(difflib.unified_diff(
            parent_text, candidate_text,
            fromfile="parent.py", tofile="candidate.py",
        )),
        encoding="utf-8",
        newline="\n",
    )
    (output_dir / "required-security-evidence-schema.json").write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    (output_dir / "packet.json").write_text(
        json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return packet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--constitution-file", type=Path, required=True)
    parser.add_argument("--release-intent", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target", default="<<TARGET_ADDRESS>>")
    parser.add_argument("--policy-fingerprint", default="<<POLICY_FINGERPRINT>>")
    parser.add_argument("--parent-source-url", default="<<PARENT_SOURCE_URL>>")
    parser.add_argument("--candidate-source-url", default="<<CANDIDATE_SOURCE_URL>>")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        build_packet(**vars(args))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"security review packet written to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
