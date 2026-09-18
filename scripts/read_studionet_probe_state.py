"""Read-only diagnostic state readback; no transaction submission."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import studionet_stable_bridge as bridge  # noqa: E402


def main() -> int:
    client = bridge.make_client()
    values = {
        "minimal_target": {
            "address": "0x9a2440C1c4c46283B6f0b02c8eC6363f3F9F496C",
            "number": bridge.read(client, "0x9a2440C1c4c46283B6f0b02c8eC6363f3F9F496C", "get_number"),
            "text": bridge.read(client, "0x9a2440C1c4c46283B6f0b02c8eC6363f3F9F496C", "get_text"),
        },
        "minimal_typed_caller": {
            "address": "0xD755eBAed78601cB11BF0723b567259dD11CE6E2",
            "last_number": bridge.read(client, "0xD755eBAed78601cB11BF0723b567259dD11CE6E2", "get_last_number"),
        },
        "upgraded_sentinelx_caller": {
            "address": "0xCe0299DAAc3997539a21059C33e44B486edE958D",
            "last_installed": bridge.read(client, "0xCe0299DAAc3997539a21059C33e44B486edE958D", "get_last_installed"),
        },
        "baseline_sentinelx_caller": {
            "address": "0x51D0A886BD4BA8D36a1961Cac7c1dA49bdF1D168",
            "last_installed": bridge.read(client, "0x51D0A886BD4BA8D36a1961Cac7c1dA49bdF1D168", "get_last_installed"),
        },
    }
    print(json.dumps(values, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
