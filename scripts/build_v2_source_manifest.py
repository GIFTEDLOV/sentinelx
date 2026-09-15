"""Write the SentinelX V2 source manifest after a source freeze."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.v2_source_manifest import MANIFEST_PATH, build_manifest, verify_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the existing manifest")
    args = parser.parse_args()
    if args.check:
        errors = verify_manifest()
        if errors:
            for error in errors:
                print(error)
            return 1
        print(f"verified {MANIFEST_PATH}")
        return 0
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(build_manifest(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
