"""Fail-closed parity check between a source file and an exact deployed dump."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> tuple[bytes, str]:
    if not path.is_file():
        raise ValueError(f"parity input is not a regular file: {path}")
    data = path.read_bytes()
    return data, hashlib.sha256(data).hexdigest()


def verify(local: Path, deployed: Path, expected_sha256: str | None = None) -> dict[str, object]:
    local_bytes, local_hash = digest(local)
    deployed_bytes, deployed_hash = digest(deployed)
    if expected_sha256 is not None and expected_sha256 != local_hash:
        raise ValueError("expected SHA-256 does not match local source bytes")
    equal = local_bytes == deployed_bytes and local_hash == deployed_hash
    result = {
        "local_sha256": local_hash,
        "deployed_sha256": deployed_hash,
        "byte_equal": equal,
        "parity": equal,
    }
    if expected_sha256 is not None:
        result["expected_sha256"] = expected_sha256
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", required=True, type=Path)
    parser.add_argument("--deployed", required=True, type=Path)
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    try:
        result = verify(args.local, args.deployed, args.expected_sha256)
    except (OSError, ValueError) as error:
        print(json.dumps({"parity": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["parity"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
