"""Run isolated GenVM v0.6 semantic validation for the frozen V2.2 sources.

The repository freezes the static linter at 0.11.0 and the semantic RC at
0.11.1rc2.  They are separate gates: the former is used by ``preflight.py``;
this command installs the pinned semantic linter into a temporary target so a
machine-level static-linter install cannot silently stand in for the semantic
check.  The validator then resolves the exact v0.6.0-rc5 GenVM bundle from
its normal cache/download path and validates the source bytes in place.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SEMANTIC_LINTER = "0.11.1rc2"
GENVM_VERSION = "v0.6.0-rc5"
CONTRACTS = (
    ROOT / "contracts" / "sentinelx_governor.py",
    ROOT / "contracts" / "protected_app_v1.py",
    ROOT / "contracts" / "protected_app_v2_safe.py",
    ROOT / "contracts" / "protected_app_v2_unsafe.py",
)
FROZEN_HASHES = {
    "sentinelx_governor.py": "5ff81c36fe5ca8d85ec76c6167c788cdde620b9d0ad98df5696db5f19b91d588",
    "protected_app_v1.py": "470c9a72c63f8ca345956299edc530bc92924eaa1708c05a767b141df05d1c4f",
    "protected_app_v2_safe.py": "72c240f0725dc314429d01f051d4b40dc906623f48ba2b38514824d7f46011e5",
    "protected_app_v2_unsafe.py": "6b3f7a0ebae0f097036f33b57b77b1d10ae2d813b7330e34ba1dab33a5010653",
}


def _verify_sources() -> None:
    for path in CONTRACTS:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != FROZEN_HASHES[path.name]:
            raise RuntimeError(f"frozen V2.2 source changed unexpectedly: {path} ({actual})")


def _install_semantic_linter(target: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "--no-deps",
         "--target", str(target), f"genvm-linter=={SEMANTIC_LINTER}"],
        cwd=ROOT, check=False, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=240,
    )
    if result.returncode != 0:
        raise RuntimeError("could not install the pinned semantic linter: " +
                           (result.stdout + result.stderr)[-2000:])


def run() -> dict[str, object]:
    _verify_sources()
    installed = importlib.metadata.version("genvm-linter")
    with tempfile.TemporaryDirectory(prefix="sentinelx-v2-semantic-") as name:
        target = Path(name)
        _install_semantic_linter(target)
        validations: dict[str, object] = {}
        for path in CONTRACTS:
            _verify_sources()
            # The validator keeps a process-global contract registry.  One
            # child per source prevents the registry from making a valid
            # multi-contract gate fail due to module reuse.
            code = (
                "from pathlib import Path; import json; "
                "from genvm_linter.validate import validate_contract; "
                f"print(json.dumps(validate_contract(Path({json.dumps(str(path))})).to_dict()))"
            )
            environment = os.environ.copy()
            environment["GENVM_VERSION"] = GENVM_VERSION
            environment["PYTHONPATH"] = os.pathsep.join(
                [str(target), environment.get("PYTHONPATH", "")]
            )
            completed = subprocess.run(
                [sys.executable, "-c", code], cwd=ROOT, env=environment,
                check=False, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=300,
            )
            output = (completed.stdout + completed.stderr).strip()
            try:
                detail = json.loads(output.splitlines()[-1])
            except (json.JSONDecodeError, IndexError) as error:
                raise RuntimeError(f"semantic validator emitted invalid output for {path.name}: {output[-2000:]}") from error
            validations[path.name] = detail
            if completed.returncode != 0 or not detail.get("ok"):
                raise RuntimeError(f"semantic validation failed for {path.name}: {detail}")
    _verify_sources()
    return {
        "schema": "sentinelx-v2-semantic-validation-v1",
        "semantic_linter": f"genvm-linter {SEMANTIC_LINTER}",
        "static_linter_installed": f"genvm-linter {installed}",
        "genvm_runner": GENVM_VERSION,
        "contracts": validations,
        "result": "PASS",
        "frozen_sources_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = run()
    except Exception as error:
        print(json.dumps({"schema": "sentinelx-v2-semantic-validation-v1",
                          "result": "FAIL", "error": f"{type(error).__name__}: {error}"},
                         indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
