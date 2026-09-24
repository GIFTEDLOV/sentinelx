"""Fail-closed proof for the intentionally exceptional stable Python stack."""

from __future__ import annotations

from importlib import metadata
import inspect
from pathlib import Path


EXPECTED = {
    "genlayer-py": "0.18.0",
    "genlayer-test": "0.29.2",
    "genvm-linter": "0.11.0",
}
REQUIRED_FIXTURES = (
    "direct_vm",
    "direct_deploy",
    "direct_alice",
    "direct_bob",
    "direct_charlie",
    "direct_owner",
    "direct_accounts",
)
REQUIRED_VM_API = (
    "mock_web",
    "mock_llm",
    "clear_mocks",
    "expect_revert",
    "snapshot",
    "revert",
    "run_validator",
)
ROOT = Path(__file__).resolve().parents[1]
RUNNER_HASH = "1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6"


def main() -> int:
    versions = {name: metadata.version(name) for name in EXPECTED}
    if versions != EXPECTED:
        raise SystemExit(f"toolchain version mismatch: {versions}")

    # Import both distributions under their actual public module names. The
    # distribution/module names differ for both packages (genlayer_py/gltest).
    import genlayer_py  # noqa: F401
    from gltest.direct import VMContext, deploy_contract, load_contract_class
    from gltest.direct import pytest_plugin

    missing_fixtures = [name for name in REQUIRED_FIXTURES if not hasattr(pytest_plugin, name)]
    missing_vm_api = [name for name in REQUIRED_VM_API if not hasattr(VMContext, name)]
    if missing_fixtures or missing_vm_api:
        raise SystemExit(
            f"Direct Mode API mismatch: fixtures={missing_fixtures}, vm={missing_vm_api}"
        )

    if "contract_path" not in inspect.signature(deploy_contract).parameters:
        raise SystemExit("direct deploy contract_path API is missing")
    if "contract_path" not in inspect.signature(load_contract_class).parameters:
        raise SystemExit("direct loader contract_path API is missing")

    # Prove the pinned runner header is still present without executing a
    # contract or contacting a network. The Direct Mode loader API is checked
    # above; the full contract execution gates run separately in CI.
    frozen = ROOT / "contracts" / "protected_app_v2_safe.py"
    first_line = frozen.read_text(encoding="utf-8").splitlines()[0]
    if RUNNER_HASH not in first_line:
        raise SystemExit("stable py-genlayer runner header is missing")

    print({"result": "PASS", "versions": versions, "fixtures": list(REQUIRED_FIXTURES), "vm_api": list(REQUIRED_VM_API), "runner": "v0.2.12"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
