"""Read-only managed-signer readback for the completed V2.3 profile."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.studionet_stable_bridge import make_client, read, read_json


GOVERNOR = "0x178Cc14e39E5873C4EaB2590B1a94b92694545ac"
SAFE_TARGET = "0x9e0e22C8f35312E75C66f0255d4559f90e4fCd09"
UNSAFE_TARGET = "0xD8F0Ce45738c86bA2C3D6c2595cFcc357Ae04920"


def main() -> int:
    client = make_client()
    result = {
        "safe_proposal": read_json(client, GOVERNOR, "get_proposal", [1]),
        "safe_policy": read_json(client, GOVERNOR, "get_target_policy", [SAFE_TARGET]),
        "safe_active_proposal": read(client, GOVERNOR, "get_active_proposal", [SAFE_TARGET]),
        "safe_installed_id": read(client, SAFE_TARGET, "get_installed_proposal_id"),
        "safe_installed_hash": read(client, SAFE_TARGET, "get_installed_candidate_hash"),
        "safe_release_history": read(client, GOVERNOR, "get_release_history", [SAFE_TARGET]),
        "unsafe_proposal": read_json(client, GOVERNOR, "get_proposal", [2]),
        "unsafe_active_proposal": read(client, GOVERNOR, "get_active_proposal", [UNSAFE_TARGET]),
        "unsafe_installed_id": read(client, UNSAFE_TARGET, "get_installed_proposal_id"),
        "unsafe_installed_hash": read(client, UNSAFE_TARGET, "get_installed_candidate_hash"),
        "unsafe_value": read(client, UNSAFE_TARGET, "get_protected_value"),
        "unsafe_nonce": read(client, UNSAFE_TARGET, "get_value_nonce"),
        "unsafe_governor": read(client, UNSAFE_TARGET, "get_upgrade_governor"),
    }
    readback_path = ROOT / "artifacts" / "studionet" / "v2.3" / "live-state-readback.json"
    readback_path.parent.mkdir(parents=True, exist_ok=True)
    readback_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
