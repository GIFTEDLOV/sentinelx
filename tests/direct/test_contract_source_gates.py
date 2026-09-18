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


def test_v2_governor_declares_bounded_attestation_modes_and_snapshot_schema():
    text = (CONTRACT_DIR / "sentinelx_governor.py").read_text(encoding="utf-8")
    assert 'SCHEMA_VERSION = "sentinelx-governor-v2.3-studionet"' in text
    assert 'STAGED_EVIDENCE_SCHEMA = "sentinelx-staged-evidence-v2"' in text
    assert 'SNAPSHOT_SCHEMA = "sentinelx-evidence-snapshot-v3"' in text
    assert 'SECURITY_OPTIONAL = "OPTIONAL"' in text
    assert 'SECURITY_REQUIRED_INDEPENDENT = "REQUIRED_INDEPENDENT"' in text
    assert 'STATUS_EVIDENCE_READY = "EVIDENCE_READY"' in text


def test_v23_confirmation_is_sender_and_authorization_bound_without_historical_view_reads():
    module = parsed("sentinelx_governor.py")
    functions = {
        node.name: node for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    confirm = ast.unparse(functions["confirm_install"])
    reconcile = ast.unparse(functions["reconcile_install"])
    assert "gl.message.sender_address != proposal.target" in confirm
    assert "policy.policy_fingerprint != proposal.policy_fingerprint" in confirm
    assert "policy.current_code_hash != proposal.parent_code_hash" in confirm
    assert "active_proposal_by_target" in confirm
    assert "LATEST_FINALIZED" not in confirm
    assert "LATEST_DECIDED" not in confirm
    assert "unsupported" in reconcile.lower()
    for name in ("protected_app_v1.py", "protected_app_v2_safe.py"):
        target = (CONTRACT_DIR / name).read_text(encoding="utf-8")
        assert "def retry_install_confirmation" in target
        assert "self.installed_candidate_hash" in target


def test_v2_policy_and_snapshot_storage_are_explicitly_bound():
    policy_fields = field_names("sentinelx_governor.py")
    assert "evidence_snapshots" in policy_fields
    text = (CONTRACT_DIR / "sentinelx_governor.py").read_text(encoding="utf-8")
    assert "security_attestation_mode: str" in text
    assert "class EvidenceSnapshotRecord" in text
    assert "class StagedEvidenceRecord" in text
    assert "staged_evidence: TreeMap[str, StagedEvidenceRecord]" in text
    assert "snapshot_digest: str" in text
    assert "evidence_snapshots: TreeMap[str, EvidenceSnapshotRecord]" in text


def test_v21_per_target_indexes_use_runtime_supported_scalar_storage():
    text = (CONTRACT_DIR / "sentinelx_governor.py").read_text(encoding="utf-8")
    assert "proposals_by_target: TreeMap[Address, str]" in text
    assert "release_history_by_target: TreeMap[Address, str]" in text
    assert "TreeMap[Address, DynArray[u256]]" not in text
    assert "DynArray[u256]()" not in text


def test_v21_governor_normalizes_runtime_address_arguments():
    text = (CONTRACT_DIR / "sentinelx_governor.py").read_text(encoding="utf-8")
    assert "if isinstance(value, Address):" in text
    assert "target_address = self._address_or_error(target, \"Target\")" in text
    assert "Address(target)" not in text


def test_v21_uses_supported_v06_nondeterministic_primitive():
    text = (CONTRACT_DIR / "sentinelx_governor.py").read_text(encoding="utf-8")
    assert text.count("gl.vm.run_nondet(leader_fn, validator_fn)") == 2
    assert "run_nondet_unsafe" not in text


def test_v2_capture_can_fetch_but_review_path_has_no_web_fetch_call():
    module = parsed("sentinelx_governor.py")
    functions = {
        node.name: node for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    capture = ast.unparse(functions["capture_evidence"])
    review = ast.unparse(functions["_review_proposal"])
    snapshot_review = ast.unparse(functions["_independent_snapshot_review"])
    assert "gl.nondet.web.get" in ast.unparse(functions["_fetch_bytes"])
    assert "gl.nondet.web.get" not in capture
    assert "gl.nondet.web.get" not in review
    assert "gl.nondet.web.get" not in snapshot_review
    assert "_independent_snapshot_review" in review
    assert "review_web_fetch_counts[proposal_id] = 0" in review


def test_v22_stages_bytes_and_only_returns_compact_capture_facts():
    module = parsed("sentinelx_governor.py")
    functions = {
        node.name: node for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    stage = ast.unparse(functions["stage_evidence"])
    capture_success = ast.unparse(functions["_capture_success"])
    capture = ast.unparse(functions["capture_evidence"])
    assert "gl.nondet.web.get" not in stage
    assert "gl.nondet.exec_prompt" not in stage
    assert "parent_source_bytes" in stage and "ci_evidence_bytes" in stage
    assert "candidate_code" in capture
    assert "parent_bytes_hex" not in capture_success
    assert "candidate_bytes_hex" not in capture_success
    assert "ci_bytes_hex" not in capture_success
    assert "security_bytes_hex" not in capture_success
    assert "parent_sha256" in capture_success and "parent_length" in capture_success
    assert "Evidence must be staged before capture" in capture


def test_v22_review_queues_before_deterministic_install_execution():
    module = parsed("sentinelx_governor.py")
    functions = {
        node.name: node for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    review = ast.unparse(functions["_review_proposal"])
    execute = ast.unparse(functions["execute_reviewed_upgrade"])
    assert "install_reviewed_upgrade" not in review
    assert "proposal.status = STATUS_UPGRADE_QUEUED" in review
    assert "proposal.status != STATUS_UPGRADE_QUEUED" in execute
    assert "install_reviewed_upgrade" in execute
    assert "emit(on='finalized')" in execute


def test_v2_target_registration_interfaces_include_attestation_mode():
    for name in ("protected_app_v1.py", "protected_app_v2_safe.py"):
        text = (CONTRACT_DIR / name).read_text(encoding="utf-8")
        assert "security_attestation_mode: str" in text
        assert "security_attestation_mode," in text


def test_registration_interface_and_emit_argument_order_is_exact():
    module = parsed("protected_app_v1.py")
    interface = next(node for node in module.body
                     if isinstance(node, ast.ClassDef) and node.name == "SentinelXGovernorInterface")
    write = next(node for node in interface.body
                 if isinstance(node, ast.ClassDef) and node.name == "Write")
    register_interface = next(node for node in write.body
                              if isinstance(node, ast.FunctionDef) and node.name == "register_target")
    assert [arg.arg for arg in register_interface.args.args[1:]] == [
        "target", "owner", "project_name", "release_constitution", "source_authority",
        "ci_authority", "security_attestation_mode", "security_authority", "source_prefix",
        "ci_prefix", "security_prefix", "current_version", "current_source_url",
        "current_code_hash", "max_evidence_age_seconds", "proposal_ttl_seconds",
        "execution_timeout_seconds",
    ]
    target = next(node for node in module.body
                  if isinstance(node, ast.ClassDef) and node.name == "ProtectedApplication")
    registration = next(node for node in target.body
                        if isinstance(node, ast.FunctionDef) and node.name == "register_with_sentinelx")
    emit = next(node for node in ast.walk(registration)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "register_target")
    assert [ast.unparse(arg) for arg in emit.args] == [
        "str(gl.message.contract_address)", "str(self.owner)", "project_name",
        "release_constitution", "source_authority", "ci_authority",
        "security_attestation_mode", "security_authority", "source_prefix", "ci_prefix",
        "security_prefix", "current_version", "current_source_url", "current_code_hash",
        "max_evidence_age_seconds", "proposal_ttl_seconds", "execution_timeout_seconds",
    ]
