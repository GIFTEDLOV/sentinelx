"""Reconcile one already-submitted diagnostic hash; never broadcasts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import studionet_stable_bridge as bridge


def main() -> int:
    operation = os.environ["SENTINELX_PROBE_OPERATION"]
    tx_hash = os.environ["SENTINELX_PROBE_TX"]
    client = bridge.make_client()
    journal_obj = bridge.journal()
    receipt, children = bridge._reconcile(client, journal_obj, operation, tx_hash)
    print(json.dumps({
        "operation": operation,
        "tx_hash": tx_hash,
        "status": bridge._status(receipt),
        "execution": bridge._execution(receipt),
        "children": children,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
