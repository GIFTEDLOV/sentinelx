"""Validate the V2.3 stable compatibility contract invariants.

This is the stable Studionet companion to the historical RC semantic gate. It
uses the pinned stable static linter, Python compilation, and AST assertions for
the runtime-specific finalized-view isolation fix. It never broadcasts.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = tuple(ROOT / "contracts" / name for name in (
    "sentinelx_governor.py", "protected_app_v1.py",
    "protected_app_v2_safe.py", "protected_app_v2_unsafe.py",
))
SEMANTIC_VECTOR = (
    "storage_layout_compatible", "public_interface_compatible",
    "user_rights_preserved", "no_privilege_escalation",
    "upgrade_authority_preserved", "consensus_integrity_preserved",
    "finality_safety_preserved", "evidence_trust_preserved",
    "fund_flow_safe", "external_fetch_surface_safe", "liveness_preserved",
    "behavioral_scope_matches_release", "migration_safety_preserved",
    "constitution_satisfied",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _functions(path: Path) -> dict[str, str]:
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name: ast.unparse(node)
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _lint(path: Path) -> dict[str, object]:
    linter = shutil.which("genvm-lint")
    if linter is None:
        candidate = Path(sys.executable).parent / "Scripts" / "genvm-lint.exe"
        linter = str(candidate) if candidate.exists() else None
    if linter is None:
        return {"ok": False, "detail": "genvm-lint executable not found"}
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [linter, "lint", str(path)], cwd=ROOT, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, check=False,
    )
    return {"ok": result.returncode == 0, "detail": (result.stdout + result.stderr).strip()}


def run() -> dict[str, object]:
    results: dict[str, object] = {"schema": "sentinelx-studionet-v23-semantic-validation-v1", "contracts": {}}
    for path in CONTRACTS:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
        results["contracts"][path.name] = {"sha256": _sha(path), "lint": _lint(path)}  # type: ignore[index]

    governor = _functions(ROOT / "contracts" / "sentinelx_governor.py")
    if "LATEST_FINALIZED" in governor["confirm_install"] or "LATEST_DECIDED" in governor["confirm_install"]:
        raise RuntimeError("confirm_install still contains a hosted historical-view selector")
    if ".view(state=" in governor["confirm_install"] or ".view(state=" in governor["reconcile_install"]:
        raise RuntimeError("stable confirmation path still performs a state-selected cross-contract view")
    if "gl.message.sender_address != proposal.target" not in governor["confirm_install"]:
        raise RuntimeError("confirmation sender authentication is missing")
    for check in (
        "policy.policy_fingerprint != proposal.policy_fingerprint",
        "policy.current_code_hash != proposal.parent_code_hash",
        "active_proposal_by_target",
    ):
        if check not in governor["confirm_install"]:
            raise RuntimeError(f"confirmation binding is missing: {check}")
    if "unsupported" not in governor["reconcile_install"].lower():
        raise RuntimeError("historical reconcile_install was not disabled explicitly")

    module = ast.parse((ROOT / "contracts" / "sentinelx_governor.py").read_text(encoding="utf-8"))
    vector = next(
        node for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SEMANTIC_VECTOR" for target in node.targets)
    )
    if tuple(ast.literal_eval(vector.value)) != SEMANTIC_VECTOR:
        raise RuntimeError("semantic vector is not the exact fourteen-field vector")

    for name in ("protected_app_v1.py", "protected_app_v2_safe.py"):
        functions = _functions(ROOT / "contracts" / name)
        retry = functions.get("retry_install_confirmation", "")
        for check in ("self.installed_proposal_id != proposal_id", "not self.installed_candidate_hash", "emit(on='finalized').confirm_install"):
            if check not in retry:
                raise RuntimeError(f"{name} retry confirmation binding is missing: {check}")

    lint_failures = {
        name: value for name, value in results["contracts"].items()  # type: ignore[union-attr]
        if not value["lint"]["ok"]  # type: ignore[index]
    }
    if lint_failures:
        raise RuntimeError(f"stable contract lint failed: {lint_failures}")
    results.update({
        "runtime_compatibility": {
            "genlayer_py": "0.18.0", "genlayer_test": "0.29.2", "genvm_runner": "v0.2.12",
            "historical_view_selectors_removed_from_confirmation": True,
            "target_originated_retry": True,
            "semantic_vector_count": 14,
        },
        "result": "PASS",
    })
    return results


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, sort_keys=True))
    except Exception as error:
        print(json.dumps({"schema": "sentinelx-studionet-v23-semantic-validation-v1", "result": "FAIL", "error": f"{type(error).__name__}: {error}"}, indent=2, sort_keys=True))
        raise SystemExit(1)
