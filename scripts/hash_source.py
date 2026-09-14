"""Hash exact source bytes for release identity checks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def hash_file(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"source path is not a regular file: {path}")
    data = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "byte_length": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(hash_file(args.path), sort_keys=True, separators=(",", ":")))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
