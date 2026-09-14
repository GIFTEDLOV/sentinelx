"""Type-check SentinelX contracts against the exact GLTest GenVM RC SDK."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = (
    ROOT / "contracts" / "sentinelx_governor.py",
    ROOT / "contracts" / "protected_app_v1.py",
    ROOT / "contracts" / "protected_app_v2_safe.py",
    ROOT / "contracts" / "protected_app_v2_unsafe.py",
)
GENVM_RC = "v0.6.0-rc3"
_SDK_PATHS: list[Path] = []


def check(path: Path) -> tuple[bool, str]:
    from gltest.direct.sdk_loader import setup_sdk_paths

    sdk_paths = list(setup_sdk_paths(path, version=GENVM_RC))
    # GLTest avoids returning paths already present in this process's
    # sys.path. Retain the exact RC paths so each contract gets the same
    # environment when checked in one invocation.
    global _SDK_PATHS
    if sdk_paths:
        _SDK_PATHS = sdk_paths
    elif _SDK_PATHS:
        sdk_paths = _SDK_PATHS
    config = {
        "extraPaths": [str(item) for item in sdk_paths],
        "typeCheckingMode": "basic",
        "reportMissingModuleSource": False,
        "reportAttributeAccessIssue": "none",
        "reportArgumentType": "none",
        "reportReturnType": "none",
        "pythonVersion": "3.12",
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as handle:
        json.dump(config, handle)
        config_path = Path(handle.name)
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    existing_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        [*(str(item) for item in sdk_paths), existing_pythonpath]
        if existing_pythonpath else [*(str(item) for item in sdk_paths)]
    )
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pyright", "--project", str(config_path),
             str(path), "--outputjson"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=240,
        )
    finally:
        config_path.unlink(missing_ok=True)
    output = result.stdout or result.stderr
    try:
        parsed = json.loads(output)
        errors = parsed.get("summary", {}).get("errorCount", 1)
        warnings = parsed.get("summary", {}).get("warningCount", 0)
        diagnostics = [
            {
                "severity": item.get("severity"),
                "message": item.get("message"),
                "line": item.get("range", {}).get("start", {}).get("line"),
            }
            for item in parsed.get("generalDiagnostics", [])[:20]
        ]
        return result.returncode == 0 and errors == 0, json.dumps(
            {"errors": errors, "warnings": warnings, "diagnostics": diagnostics,
             "sdk_paths": [str(item) for item in sdk_paths]}, sort_keys=True
        )
    except json.JSONDecodeError:
        return False, output[-4000:]


def main() -> int:
    results: dict[str, object] = {"genvm_rc": GENVM_RC, "ok": True, "contracts": {}}
    for path in CONTRACTS:
        try:
            ok, detail = check(path)
        except Exception as error:
            ok, detail = False, str(error)
        results["contracts"][path.name] = {"ok": ok, "detail": detail}  # type: ignore[index]
        results["ok"] = bool(results["ok"]) and ok
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
