"""Fail-closed Phase 1 verification for SentinelX.

The PASS artifact is written only after every local deterministic gate has
passed. This script does not deploy, broadcast, contact a wallet, or create
transaction evidence.
"""

from __future__ import annotations

import ast
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = (
    ROOT / "contracts" / "sentinelx_governor.py",
    ROOT / "contracts" / "protected_app_v1.py",
    ROOT / "contracts" / "protected_app_v2_safe.py",
    ROOT / "contracts" / "protected_app_v2_unsafe.py",
)
EXPECTED_RPC = "https://studio-dev.genlayer.com/api"
EXPECTED_CHAIN_ID = 61997
EXPECTED_CLI = "0.40.0-rc.3"
EXPECTED_JS = "2.0.0-rc.1"
EXPECTED_PY = "0.19.0rc2"
EXPECTED_GLTEST = "0.30.0rc2"
EXPECTED_LINT = "0.11.0"
EXPECTED_VECTOR_COUNT = 14
PASS_ARTIFACT = ROOT / "artifacts" / "preflight-pass.json"


def command_result(command: list[str], *, timeout: int = 180) -> tuple[bool, str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["GENVM_VERSION"] = "v0.6.0-rc3"
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output[-4000:]


def package_version(name: str) -> str:
    return importlib.metadata.version(name)


def check_network() -> dict[str, Any]:
    from genlayer_py.chains import studio_devnet

    rpc = studio_devnet.rpc_urls["default"]["http"][0]
    return {"rpc": rpc, "chain_id": studio_devnet.id,
            "ok": rpc == EXPECTED_RPC and studio_devnet.id == EXPECTED_CHAIN_ID}


def find_linter() -> str | None:
    found = shutil.which("genvm-lint")
    if found:
        return found
    known = Path(sys.executable).parent / "Scripts" / "genvm-lint.exe"
    return str(known) if known.exists() else None


def find_cli() -> str | None:
    found = shutil.which("genlayer")
    if found:
        return found
    known = Path(os.environ.get("APPDATA", "")) / "npm" / "genlayer.cmd"
    return str(known) if known.exists() else None


def main() -> int:
    gates: dict[str, Any] = {}
    try:
        cli = find_cli()
        cli_output = command_result([cli, "--version"], timeout=30)[1] if cli else "CLI not found"
        versions = {
            "genlayer_cli": cli_output,
            "genlayer_js_selected": EXPECTED_JS,
            "genlayer_py": package_version("genlayer-py"),
            "gltest": package_version("genlayer-test"),
            "genvm_lint": package_version("genvm-linter"),
            "pytest": package_version("pytest"),
            "pyright": package_version("pyright"),
        }
        gates["tool_versions"] = {
            **versions,
            "ok": (cli is not None and EXPECTED_CLI in versions["genlayer_cli"]
                   and versions["genlayer_py"] == EXPECTED_PY
                   and versions["gltest"] == EXPECTED_GLTEST
                   and versions["genvm_lint"] == EXPECTED_LINT),
        }
        gates["network"] = check_network()
    except Exception as error:
        gates["tool_versions"] = {"ok": False, "error": str(error)}
        gates["network"] = {"ok": False, "error": str(error)}

    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from scripts.v2_source_manifest import verify_manifest

        manifest_errors = verify_manifest()
        gates["v2_source_manifest"] = {"ok": not manifest_errors, "errors": manifest_errors}
    except Exception as error:
        gates["v2_source_manifest"] = {"ok": False, "errors": [str(error)]}

    parse_ok = True
    for path in CONTRACTS:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as error:
            parse_ok = False
            gates.setdefault("parse", {})[path.name] = str(error)
    gates["parse"] = {"ok": parse_ok, **gates.get("parse", {})}

    linter = find_linter()
    lint_ok = linter is not None
    lint_results: dict[str, Any] = {}
    if linter:
        for path in CONTRACTS:
            ok, output = command_result([linter, "lint", str(path)], timeout=60)
            lint_results[path.name] = {"ok": ok, "output": output}
            lint_ok = lint_ok and ok
    gates["lint"] = {"ok": lint_ok, "results": lint_results}

    typecheck_ok, typecheck_output = command_result(
        [sys.executable, "scripts/typecheck_contracts.py"], timeout=900
    )
    gates["typecheck"] = {"ok": typecheck_ok, "output": typecheck_output}

    tests_ok, test_output = command_result(
        [sys.executable, "-m", "pytest", "tests/direct", "-q", "--tb=short"], timeout=120
    )
    passed_match = re.search(r"(\d+) passed", test_output)
    gates["direct_tests"] = {
        "ok": tests_ok,
        "count": int(passed_match.group(1)) if passed_match else 0,
        "output": test_output,
    }

    python_typecheck_ok, python_typecheck_output = command_result(
        [sys.executable, "-m", "pyright", "direct", "scripts", "tests", "--outputjson"],
        timeout=120,
    )
    gates["python_typecheck"] = {
        "ok": python_typecheck_ok,
        "output": python_typecheck_output,
    }

    governor_text = (ROOT / "contracts" / "sentinelx_governor.py").read_text(encoding="utf-8")
    safe_text = (ROOT / "contracts" / "protected_app_v2_safe.py").read_text(encoding="utf-8")
    unsafe_text = (ROOT / "contracts" / "protected_app_v2_unsafe.py").read_text(encoding="utf-8")
    vector_count = len(re.findall(r'"[a-z_]+"', governor_text.split("SEMANTIC_VECTOR =", 1)[1].split(")", 1)[0])) if "SEMANTIC_VECTOR =" in governor_text else 0
    gates["semantic_vector"] = {
        "count": vector_count,
        "exact_count": EXPECTED_VECTOR_COUNT,
        "safe_candidate_present": "release_note" in safe_text,
        "unsafe_candidate_test_only": "TEST-ONLY" in unsafe_text,
        "ok": (vector_count == EXPECTED_VECTOR_COUNT and "release_note" in safe_text
               and "TEST-ONLY" in unsafe_text),
    }

    all_ok = all(bool(value.get("ok")) for value in gates.values())
    result = {
        "schema": "sentinelx-preflight-v1",
        "network": gates.get("network"),
        "tool_versions": gates.get("tool_versions"),
        "gates": gates,
        "ok": all_ok,
        "deployment_attempted": False,
        "transaction_evidence_generated": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if not all_ok:
        PASS_ARTIFACT.unlink(missing_ok=True)
        return 1
    PASS_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    PASS_ARTIFACT.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
