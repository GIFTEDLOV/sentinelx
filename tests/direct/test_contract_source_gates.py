from __future__ import annotations

import ast
from pathlib import Path

from direct.sentinelx_model import SEMANTIC_VECTOR


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "contracts"


def parsed(name: str) -> ast.Module:
    return ast.parse((CONTRACT_DIR / name).read_text(encoding="utf-8"), filename=name)


def contract_class(module: ast.Module) -> ast.ClassDef:
    classes = [node for node in module.body if isinstance(node, ast.ClassDef)]
    return next(node for node in classes if node.name.startswith("Protected") or node.name.endswith("Governor"))


def field_names(name: str) -> list[str]:
    result: list[str] = []
    for node in contract_class(parsed(name)).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            result.append(node.target.id)
    return result


def test_all_production_contracts_parse_as_python():
    for name in ("sentinelx_governor.py", "protected_app_v1.py",
                 "protected_app_v2_safe.py", "protected_app_v2_unsafe.py"):
        assert isinstance(parsed(name), ast.Module)


def test_governor_declares_exact_fourteen_vector_fields():
    module = parsed("sentinelx_governor.py")
    assignment = next(node for node in module.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "SEMANTIC_VECTOR"
                              for target in node.targets))
    assert tuple(ast.literal_eval(assignment.value)) == SEMANTIC_VECTOR


def test_v1_storage_prefix_is_explicit_and_owner_is_not_an_upgrader():
    names = field_names("protected_app_v1.py")
    assert names == ["owner", "sentinelx_governor", "application_name",
                     "protected_value", "value_nonce", "installed_proposal_id",
                     "installed_candidate_hash", "registered_with_sentinelx"]
    text = (CONTRACT_DIR / "protected_app_v1.py").read_text(encoding="utf-8")
    assert "root.upgraders.get().append(sentinelx_governor)" in text
    assert "root.upgraders.get().append(self.owner)" not in text


def test_safe_v2_appends_only_a_compatible_feature_field():
    names = field_names("protected_app_v2_safe.py")
    assert names[:8] == field_names("protected_app_v1.py")
    assert names[-1] == "release_note"


def test_unsafe_v2_contains_multiple_explicit_negative_controls():
    text = (CONTRACT_DIR / "protected_app_v2_unsafe.py").read_text(encoding="utf-8")
    assert "TEST-ONLY" in text
    assert "owner_replace_code" in text
    assert "rewrite_governor" in text
    assert "drain_value" in text
    assert field_names("protected_app_v2_unsafe.py")[0] == "emergency_admin"


def test_target_upgrade_path_checks_governor_sender_and_live_authorization():
    for name in ("protected_app_v1.py", "protected_app_v2_safe.py"):
        text = (CONTRACT_DIR / name).read_text(encoding="utf-8")
        assert "sender_address != self.sentinelx_governor" in text
        assert "is_upgrade_authorized" in text
        assert "confirm_install" in text
