"""Adversarial mutation suite for the frozen SentinelX V2 boundary.

Each mutation is applied to a temporary copy of the production contract and,
where the deterministic V2 oracle can exercise the invariant, its temporary
oracle copy.  The production contracts are never imported from, rewritten, or
used as scratch files.  A mutation is killed only when its focused behavioral
probe or a structural contract gate detects the weakened protection.

This is intentionally a standalone runner instead of a pytest plugin: CI can
run it directly, and an authenticated CI envelope can truthfully identify the
adversarial gate as a separate result from the ordinary direct suite.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import ModuleType
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
GOVERNOR = ROOT / "contracts" / "sentinelx_governor.py"
TARGET = ROOT / "contracts" / "protected_app_v1.py"
ORACLE = ROOT / "direct" / "sentinelx_v2_model.py"
ORACLE_BASE = ROOT / "direct" / "sentinelx_model.py"
FROZEN_HASHES = {
    GOVERNOR: "8bd7dd0d5bedfb671e478f6cfc0a03aaf99328f5c4d93162c2784965035f7fcd",
    ROOT / "contracts" / "protected_app_v1.py": "470c9a72c63f8ca345956299edc530bc92924eaa1708c05a767b141df05d1c4f",
    ROOT / "contracts" / "protected_app_v2_safe.py": "72c240f0725dc314429d01f051d4b40dc906623f48ba2b38514824d7f46011e5",
    ROOT / "contracts" / "protected_app_v2_unsafe.py": "6b3f7a0ebae0f097036f33b57b77b1d10ae2d813b7330e34ba1dab33a5010653",
}

TARGET_ADDRESS = "0x" + "1" * 40
OWNER_ADDRESS = "0x" + "2" * 40
SOURCE_PREFIX = "https://raw.githubusercontent.com/source-org/sentinelx/"
CI_PREFIX = "https://raw.githubusercontent.com/ci-org/sentinelx-ci/"
SECURITY_PREFIX = "https://raw.githubusercontent.com/security-org/reviews/"
PARENT = b"parent frozen source bytes\n"
CANDIDATE = b"candidate frozen source bytes\n"
NOW = 1_700_000_000


@dataclass(frozen=True)
class Mutation:
    number: int
    name: str
    contract_path: Path
    contract_mutator: Callable[[str], str]
    oracle_mutator: Callable[[str], str] | None
    probe: Callable[[ModuleType], None] | None
    gate: Callable[[dict[str, str]], None] | None


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise AssertionError(f"{label}: expected one mutation site, found {count}")
    return text.replace(old, new, 1)


def _replace_first(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise AssertionError(f"{label}: mutation site not found")
    return text.replace(old, new, 1)


def _replace_many(text: str, replacements: list[tuple[str, str, str]]) -> str:
    for old, new, label in replacements:
        text = _replace_once(text, old, new, label)
    return text


def _source(old: str, new: str, label: str) -> Callable[[str], str]:
    return lambda text: _replace_once(text, old, new, label)


def _source_many(replacements: list[tuple[str, str, str]]) -> Callable[[str], str]:
    return lambda text: _replace_many(text, replacements)


def _mutate_required_contract(text: str) -> str:
    text = _replace_first(
        text,
        '        if self._security_required(policy) and not security_supplied:\n            raise gl.vm.UserError("Required independent security evidence is missing")\n',
        '        if False:\n            raise gl.vm.UserError("Required independent security evidence is missing")\n',
        "required security proposal",
    )
    return _replace_once(
        text,
        '        elif self._security_required(policy):\n            return self._capture_error(proposal, "SECURITY_REQUIRED_MISSING")\n',
        '        elif False:\n            return self._capture_error(proposal, "SECURITY_REQUIRED_MISSING")\n',
        "required security capture",
    )


def _copy_and_mutate(root: Path, mutation: Mutation) -> tuple[Path, Path | None]:
    contracts = root / "contracts"
    direct = root / "direct"
    contracts.mkdir(parents=True)
    direct.mkdir(parents=True)
    contract_copy = contracts / mutation.contract_path.name
    contract_copy.write_text(
        mutation.contract_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
    )
    contract_copy.write_text(
        mutation.contract_mutator(contract_copy.read_text(encoding="utf-8")),
        encoding="utf-8", newline="\n",
    )
    oracle_copy: Path | None = None
    if mutation.oracle_mutator is not None:
        oracle_copy = direct / ORACLE.name
        oracle_copy.write_text(
            mutation.oracle_mutator(ORACLE.read_text(encoding="utf-8")),
            encoding="utf-8", newline="\n",
        )
        shutil.copy2(ORACLE_BASE, direct / ORACLE_BASE.name)
        (direct / "__init__.py").write_text("", encoding="utf-8", newline="\n")
    return contract_copy, oracle_copy


def _load_oracle(root: Path, mutation: Mutation) -> ModuleType:
    package_name = f"sentinelx_mutation_{mutation.number}"
    package_dir = root / package_name
    package_dir.mkdir()
    shutil.copy2(root / "direct" / ORACLE.name, package_dir / ORACLE.name)
    shutil.copy2(root / "direct" / ORACLE_BASE.name, package_dir / ORACLE_BASE.name)
    (package_dir / "__init__.py").write_text("", encoding="utf-8", newline="\n")
    sys.path.insert(0, str(root))
    try:
        return importlib.import_module(f"{package_name}.{ORACLE.stem}")
    except Exception:
        sys.path.pop(0)
        raise


def _unload_oracle(module: ModuleType) -> None:
    prefix = module.__name__.split(".", 1)[0]
    for name in list(sys.modules):
        if name == prefix or name.startswith(prefix + "."):
            del sys.modules[name]
    if module.__file__:
        import_root = str(Path(module.__file__).parents[1])
        if import_root in sys.path:
            sys.path.remove(import_root)


def _expect_error(call: Callable[[], object], label: str) -> None:
    try:
        call()
    except Exception:
        return
    raise AssertionError(f"{label}: weakened invariant was accepted")


def _constitution() -> str:
    return json.dumps({
        "version": "sentinelx-release-constitution-v1",
        "required_vector": [
            "storage_layout_compatible", "public_interface_compatible",
            "user_rights_preserved", "no_privilege_escalation",
            "upgrade_authority_preserved", "consensus_integrity_preserved",
            "finality_safety_preserved", "evidence_trust_preserved",
            "fund_flow_safe", "external_fetch_surface_safe",
            "liveness_preserved", "behavioral_scope_matches_release",
            "migration_safety_preserved", "constitution_satisfied",
        ],
        "rules": ["authenticate evidence", "preserve storage", "preserve owner",
                  "preserve liveness", "safe funds", "finalized installation"],
    }, separators=(",", ":"))


def _ci_body(proposal: Any, *, published: int = NOW - 10,
             expires: int = NOW + 3_600, **overrides: object) -> bytes:
    value = {
        "schema": "sentinelx-evidence-v1", "kind": "ci",
        "evidence_id": proposal.ci_evidence_id, "issuer": "ci-authority",
        "target": TARGET_ADDRESS,
        "parent_sha256": proposal.parent_code_hash,
        "candidate_sha256": proposal.candidate_code_hash,
        "policy_fingerprint": proposal.policy_fingerprint,
        "published_at": published, "expires_at": expires,
        "checks": {name: True for name in (
            "genvm_lint", "typecheck", "schema", "direct_tests",
            "adversarial_tests", "source_parity", "transaction_safety",
        )},
    }
    value.update(overrides)
    return json.dumps(value).encode()


def _prepared(module: ModuleType, *, mode: str | None = None,
              security: bool = False, candidate: bytes = CANDIDATE,
              candidate_url: str | None = None, ci_id: str = "ci-proof-0001") -> tuple[Any, Any]:
    mode = mode or module.OPTIONAL
    model = module.SentinelXV2Model(NOW)
    security_configured = security or mode == module.REQUIRED_INDEPENDENT
    security_url = SECURITY_PREFIX + "e" * 40 + "/security.json" if security else ""
    security_id = "security-proof-0001" if security else ""
    model.register_target(
        target=TARGET_ADDRESS, owner=OWNER_ADDRESS, project_name="Mutation target",
        constitution=_constitution(), source_authority="source-authority",
        ci_authority="ci-authority", security_authority="security-authority" if security_configured else "",
        source_prefix=SOURCE_PREFIX, ci_prefix=CI_PREFIX,
        security_prefix=SECURITY_PREFIX if security_configured else "",
        security_attestation_mode=mode, current_version="1.0.0",
        current_source_url=SOURCE_PREFIX + "a" * 40 + "/protected_app_v1.py",
        current_code_hash=module.sha256_hex(PARENT), caller=TARGET_ADDRESS,
    )
    proposal = model.create_proposal(
        target=TARGET_ADDRESS, candidate_version="2.0.0",
        candidate_source_url=candidate_url or SOURCE_PREFIX + "b" * 40 + "/protected_app_v2_safe.py",
        candidate_code=candidate, ci_evidence_url=CI_PREFIX + "c" * 40 + "/ci.json",
        ci_evidence_id=ci_id, security_evidence_url=security_url,
        security_evidence_id=security_id, caller=OWNER_ADDRESS,
    )
    return model, proposal


def _web(proposal: Any, *, parent: bytes = PARENT, candidate: bytes = CANDIDATE,
         ci: bytes | None = None) -> dict[str, bytes]:
    return {
        proposal.parent_source_url: parent,
        proposal.candidate_source_url: candidate,
        proposal.ci_evidence_url: ci or _ci_body(proposal),
    }


def _all_true(module: ModuleType) -> dict[str, bool]:
    return {key: True for key in module.SEMANTIC_VECTOR}


def _capture(module: ModuleType) -> tuple[Any, Any]:
    model, proposal = _prepared(module)
    result = model.capture_evidence(proposal.proposal_id, web=_web(proposal), caller=OWNER_ADDRESS)
    if result != module.EVIDENCE_READY:
        raise AssertionError(f"fixture capture did not reach EVIDENCE_READY: {result}")
    return model, proposal


def probe_parent_hash(module: ModuleType) -> None:
    model, proposal = _prepared(module)
    result = model.capture_evidence(
        proposal.proposal_id, web=_web(proposal, parent=b"tampered"), caller=OWNER_ADDRESS
    )
    if result == module.EVIDENCE_READY:
        raise AssertionError("parent hash mismatch was accepted")


def probe_candidate_frozen(module: ModuleType) -> None:
    model, proposal = _prepared(module)
    proposal.candidate_code = b"changed frozen bytes"
    result = model.capture_evidence(
        proposal.proposal_id, web=_web(proposal), caller=OWNER_ADDRESS
    )
    if result == module.EVIDENCE_READY:
        raise AssertionError("candidate/frozen-byte mismatch was accepted")


def probe_snapshot_write_once(module: ModuleType) -> None:
    model, proposal = _capture(module)
    proposal.status = module.REPAIR
    _expect_error(lambda: model.capture_evidence(
        proposal.proposal_id, web=_web(proposal), caller=OWNER_ADDRESS
    ), "snapshot write-once")


def probe_snapshot_binding(module: ModuleType) -> None:
    model, proposal = _capture(module)
    snapshot = model.snapshots[proposal.evidence_identity]
    altered = type(snapshot)(**{**snapshot.__dict__, "proposal_id": proposal.proposal_id + 100})
    altered = type(altered)(**{**altered.__dict__, "snapshot_digest": model._snapshot_digest(altered)})
    model.snapshots[proposal.evidence_identity] = altered
    if model.review(proposal.proposal_id, semantic=_all_true(module), caller=OWNER_ADDRESS) != module.REPAIR:
        raise AssertionError("proposal-to-snapshot binding was not enforced")


def probe_transport_identity(module: ModuleType) -> None:
    model, proposal = _prepared(module)
    identity = proposal.evidence_identity
    model.capture_evidence(proposal.proposal_id, web=_web(proposal, candidate=b"wrong"), caller=OWNER_ADDRESS)
    model.repair_evidence(
        proposal.proposal_id, candidate_source_url=SOURCE_PREFIX + "d" * 40 + "/mirror.py",
        ci_evidence_url=proposal.ci_evidence_url, ci_evidence_id=proposal.ci_evidence_id,
        caller=OWNER_ADDRESS,
    )
    if proposal.evidence_identity != identity:
        raise AssertionError("transport URL changed evidence identity")


def probe_mirror_bytes(module: ModuleType) -> None:
    model, proposal = _prepared(module)
    model.capture_evidence(proposal.proposal_id, web=_web(proposal, candidate=b"wrong"), caller=OWNER_ADDRESS)
    # The weakened mutant may have accepted the first bad capture.  Put the
    # fixture into the repair state so this probe tests the mirror recovery
    # boundary itself, independently of the initial failure classification.
    proposal.status = module.REPAIR
    model.repair_evidence(
        proposal.proposal_id, candidate_source_url=SOURCE_PREFIX + "d" * 40 + "/mirror.py",
        ci_evidence_url=proposal.ci_evidence_url, ci_evidence_id="ci-proof-0002",
        caller=OWNER_ADDRESS,
    )
    _expect_error(lambda: model.capture_evidence(
        proposal.proposal_id,
        web={proposal.parent_source_url: PARENT, proposal.candidate_source_url: b"tampered",
             proposal.ci_evidence_url: _ci_body(proposal)}, caller=OWNER_ADDRESS,
    ), "mirror byte authentication")


def probe_review_before_ready(module: ModuleType) -> None:
    model, proposal = _prepared(module)
    _expect_error(lambda: model.review(
        proposal.proposal_id, semantic=_all_true(module), caller=OWNER_ADDRESS
    ), "review before evidence ready")


def probe_ci_field(module: ModuleType, field: str) -> None:
    model, proposal = _prepared(module)
    bad = json.loads(_ci_body(proposal))
    bad[field] = "wrong" if field in {"issuer", "target", "parent_sha256", "candidate_sha256", "policy_fingerprint"} else bad[field]
    if model.capture_evidence(proposal.proposal_id, web=_web(proposal, ci=json.dumps(bad).encode()), caller=OWNER_ADDRESS) != module.REPAIR:
        raise AssertionError(f"CI {field} binding was not enforced")


def probe_freshness(module: ModuleType) -> None:
    model, proposal = _prepared(module)
    if model.capture_evidence(
        proposal.proposal_id, web=_web(proposal, ci=_ci_body(proposal, published=NOW - 100_000, expires=NOW - 1)),
        caller=OWNER_ADDRESS,
    ) != module.REPAIR:
        raise AssertionError("evidence freshness was not enforced")


def probe_required_security(module: ModuleType) -> None:
    try:
        model, proposal = _prepared(module, mode=module.REQUIRED_INDEPENDENT, security=False)
        result = model.capture_evidence(proposal.proposal_id, web=_web(proposal), caller=OWNER_ADDRESS)
    except Exception:
        return
    if result == module.EVIDENCE_READY:
        raise AssertionError("REQUIRED_INDEPENDENT accepted no security artifact")


def probe_same_owner_security(module: ModuleType) -> None:
    model = module.SentinelXV2Model(NOW)
    _expect_error(lambda: model.register_target(
        target=TARGET_ADDRESS, owner=OWNER_ADDRESS, project_name="Mutation target",
        constitution=_constitution(), source_authority="source-authority", ci_authority="ci-authority",
        security_authority="security-authority", source_prefix=SOURCE_PREFIX,
        ci_prefix=CI_PREFIX, security_prefix="https://raw.githubusercontent.com/source-org/reviews/",
        security_attestation_mode=module.REQUIRED_INDEPENDENT,
        current_version="1.0.0", current_source_url=SOURCE_PREFIX + "a" * 40 + "/old.py",
        current_code_hash=module.sha256_hex(PARENT), caller=TARGET_ADDRESS,
    ), "same-owner independent publisher")


def probe_optional_disclaimer(module: ModuleType) -> None:
    model, proposal = _capture(module)
    prompt = model.semantic_prompt(proposal.proposal_id)
    if "NO_EXTERNAL_SECURITY_AUDIT_SUPPLIED" not in prompt:
        raise AssertionError("OPTIONAL mode falsely claimed independent security")


def probe_repair_frozen(module: ModuleType) -> None:
    model, proposal = _prepared(module)
    original = (proposal.parent_code_hash, proposal.candidate_code, proposal.candidate_code_hash,
                proposal.policy_fingerprint)
    model.capture_evidence(proposal.proposal_id, web=_web(proposal, candidate=b"wrong"), caller=OWNER_ADDRESS)
    model.repair_evidence(
        proposal.proposal_id, candidate_source_url=SOURCE_PREFIX + "d" * 40 + "/mirror.py",
        ci_evidence_url=proposal.ci_evidence_url, ci_evidence_id="ci-proof-0002",
        caller=OWNER_ADDRESS,
    )
    if (proposal.parent_code_hash, proposal.candidate_code, proposal.candidate_code_hash,
            proposal.policy_fingerprint) != original:
        raise AssertionError("repair modified a frozen candidate/parent/policy field")


def probe_vector_consensus(module: ModuleType) -> None:
    model, proposal = _capture(module)
    leader = _all_true(module)
    validator = dict(leader)
    validator[module.SEMANTIC_VECTOR[0]] = False
    if model.review_consensus(proposal.proposal_id, leader=leader, validator=validator, caller=OWNER_ADDRESS) != module.RETRY:
        raise AssertionError("validator disagreement on a semantic field was accepted")


def probe_partial_vector(module: ModuleType) -> None:
    model, proposal = _capture(module)
    checks = _all_true(module)
    checks[module.SEMANTIC_VECTOR[0]] = False
    if model.review(proposal.proposal_id, semantic=checks, caller=OWNER_ADDRESS) != module.REJECTED:
        raise AssertionError("13/14 semantic fields were approved")


def probe_malformed_output(module: ModuleType) -> None:
    model, proposal = _capture(module)
    checks = _all_true(module)
    checks["extra_untrusted_field"] = True
    if model.review(proposal.proposal_id, semantic=checks, caller=OWNER_ADDRESS) != module.RETRY:
        raise AssertionError("extra model output was accepted")


def probe_validator_recompute(module: ModuleType) -> None:
    probe_vector_consensus(module)


def probe_late_authorization(module: ModuleType) -> None:
    model, proposal = _capture(module)
    if model.review(proposal.proposal_id, semantic=_all_true(module), caller=OWNER_ADDRESS) != module.QUEUED:
        raise AssertionError("fixture review did not queue")
    model.now = proposal.execution_deadline + 1
    _expect_error(lambda: model.confirm_install(proposal.proposal_id), "late execution authorization")


def probe_active_collision(module: ModuleType) -> None:
    model, first = _prepared(module)
    _expect_error(lambda: model.create_proposal(
        target=TARGET_ADDRESS, candidate_version="3.0.0",
        candidate_source_url=SOURCE_PREFIX + "e" * 40 + "/next.py", candidate_code=b"another",
        ci_evidence_url=CI_PREFIX + "f" * 40 + "/ci.json", ci_evidence_id="ci-proof-0002",
        caller=OWNER_ADDRESS,
    ), "active proposal collision")
    assert first.proposal_id == model.active[TARGET_ADDRESS]


def probe_global_replay(module: ModuleType) -> None:
    model, first = _prepared(module)
    # Represent the finalized cancellation effect without profiling an
    # unrelated recovery method in the mutation fixture.
    model.proposals[first.proposal_id].status = "CANCELLED"
    model.active[TARGET_ADDRESS] = 0
    _expect_error(lambda: model.create_proposal(
        target=TARGET_ADDRESS, candidate_version="3.0.0",
        candidate_source_url=SOURCE_PREFIX + "e" * 40 + "/next.py", candidate_code=b"another",
        ci_evidence_url=CI_PREFIX + "f" * 40 + "/ci.json", ci_evidence_id="ci-proof-0001",
        caller=OWNER_ADDRESS,
    ), "global evidence ID replay")


def probe_post_verified_mutation(module: ModuleType) -> None:
    model, proposal = _capture(module)
    model.review(proposal.proposal_id, semantic=_all_true(module), caller=OWNER_ADDRESS)
    model.confirm_install(proposal.proposal_id)
    _expect_error(lambda: model.repair_evidence(
        proposal.proposal_id, candidate_source_url=SOURCE_PREFIX + "d" * 40 + "/mirror.py",
        ci_evidence_url=proposal.ci_evidence_url, ci_evidence_id="ci-proof-0002",
        caller=OWNER_ADDRESS,
    ), "post-VERIFIED proposal mutation")


def _registration_args(module: ModuleType) -> dict[str, object]:
    return {
        "project_name": "Mutation target", "constitution": _constitution(),
        "source_authority": "source-authority", "ci_authority": "ci-authority",
        "security_authority": "", "source_prefix": SOURCE_PREFIX,
        "ci_prefix": CI_PREFIX, "security_prefix": "",
        "security_attestation_mode": module.OPTIONAL, "current_version": "1.0.0",
        "current_source_url": SOURCE_PREFIX + "a" * 40 + "/protected_app_v1.py",
        "current_code_hash": module.sha256_hex(PARENT), "max_age": 86_400,
        "proposal_ttl": 3_600, "execution_timeout": 3_600,
    }


def probe_no_early_registration_flag(module: ModuleType) -> None:
    governor = module.SentinelXV2Model(NOW)
    target = module.SentinelXV2TargetModel(governor, TARGET_ADDRESS, OWNER_ADDRESS)
    target.register_with_sentinelx(caller=OWNER_ADDRESS, **_registration_args(module))
    if target.registered_with_sentinelx:
        raise AssertionError("registration flag was written before child finality")
    if governor.is_target_registered(TARGET_ADDRESS):
        raise AssertionError("failed registration created a governor policy")


def probe_local_flag_authority(module: ModuleType) -> None:
    governor = module.SentinelXV2Model(NOW)
    target = module.SentinelXV2TargetModel(governor, TARGET_ADDRESS, OWNER_ADDRESS)
    target.registered_with_sentinelx = True
    target.register_with_sentinelx(caller=OWNER_ADDRESS, **_registration_args(module))


def probe_retry_after_registration_failure(module: ModuleType) -> None:
    governor = module.SentinelXV2Model(NOW)
    target = module.SentinelXV2TargetModel(governor, TARGET_ADDRESS, OWNER_ADDRESS)
    args = _registration_args(module)
    target.register_with_sentinelx(caller=OWNER_ADDRESS, **args)
    if target.finalize_registration_child(success=False):
        raise AssertionError("failed registration child unexpectedly succeeded")
    target.register_with_sentinelx(caller=OWNER_ADDRESS, **args)


def probe_derived_registration(module: ModuleType) -> None:
    governor = module.SentinelXV2Model(NOW)
    target = module.SentinelXV2TargetModel(governor, TARGET_ADDRESS, OWNER_ADDRESS)
    target.registered_with_sentinelx = True
    if target.is_registered_with_sentinelx():
        raise AssertionError("legacy target flag falsely reported registration")


def probe_duplicate_policy_registration(module: ModuleType) -> None:
    model = module.SentinelXV2Model(NOW)
    args = _registration_args(module)
    args.update({"target": TARGET_ADDRESS, "owner": OWNER_ADDRESS, "caller": TARGET_ADDRESS})
    model.register_target(**args)
    _expect_error(lambda: model.register_target(**args), "duplicate governor policy")


def _ast_gate(path: Path, assertion: Callable[[dict[str, str]], None]) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    functions: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.setdefault(node.name, ast.unparse(node))
    assertion(functions)


def gate_parent(functions: dict[str, str]) -> None:
    body = functions["_independent_capture"]
    assert "_sha256_hex(parent_bytes) != proposal.parent_code_hash" in body


def gate_candidate_equality(functions: dict[str, str]) -> None:
    assert "candidate_bytes != proposal.candidate_code" in functions["_independent_capture"]


def gate_write_once(functions: dict[str, str]) -> None:
    body = functions["capture_evidence"]
    assert "proposal.evidence_set_hash in self.evidence_snapshots" in body


def gate_snapshot_binding(functions: dict[str, str]) -> None:
    body = functions["_snapshot_is_intact"]
    assert "snapshot.proposal_id != proposal.proposal_id" in body
    assert "snapshot.target != proposal.target" in body


def gate_transport_identity(functions: dict[str, str]) -> None:
    body = functions["_evidence_set_hash"]
    assert "candidate_source_url" not in body and "parent_source_url" not in body


def gate_mirror(functions: dict[str, str]) -> None:
    body = functions["_independent_capture"]
    assert "_sha256_hex(candidate_bytes) != proposal.candidate_code_hash" in body
    assert "candidate_bytes != proposal.candidate_code" in body
    assert "_sha256_hex(proposal.candidate_code) != proposal.candidate_code_hash" in body


def gate_no_review_fetch(functions: dict[str, str]) -> None:
    assert "gl.nondet.web.get" not in functions["_independent_snapshot_review"]


def gate_review_status(functions: dict[str, str]) -> None:
    body = functions["review_proposal"]
    assert "STATUS_EVIDENCE_READY" in body and "STATUS_REVIEW_RETRY_REQUIRED" in body
    assert "STATUS_PROPOSED" not in body


def gate_ci_field(field: str) -> Callable[[dict[str, str]], None]:
    def check(functions: dict[str, str]) -> None:
        body = functions["_evidence_error"]
        assert f'obj["{field}"] !=' in body
    return check


def gate_freshness(functions: dict[str, str]) -> None:
    body = functions["_evidence_error"]
    assert "published > now" in body and "expires < now" in body


def gate_security_independence(functions: dict[str, str]) -> None:
    body = functions["register_target"]
    assert "raw_owner(source_prefix).lower() == self._raw_owner(security_prefix).lower()" in body


def gate_optional_disclaimer(functions: dict[str, str]) -> None:
    assert "NO_EXTERNAL_SECURITY_AUDIT_SUPPLIED" in functions["_independent_snapshot_review"]


def gate_repair_frozen(functions: dict[str, str]) -> None:
    body = functions["repair_evidence"]
    assert "proposal.candidate_code =" not in body
    assert "proposal.candidate_code_hash =" not in body
    assert "proposal.parent_code_hash =" not in body


def gate_vector_exact(functions: dict[str, str]) -> None:
    body = functions["_same_review_result"]
    assert "for key in SEMANTIC_VECTOR:" in body
    assert "SEMANTIC_VECTOR[1:]" not in body


def gate_partial_vector(functions: dict[str, str]) -> None:
    body = functions["_review_decision"]
    assert "approved = approved and checks[key]" in body


def gate_exact_output(functions: dict[str, str]) -> None:
    assert "len(value) != len(SEMANTIC_VECTOR)" in functions["_validate_semantic_vector"]


def gate_validator(functions: dict[str, str]) -> None:
    body = functions["_review_proposal"]
    assert "validator_result" in body and "_same_review_result" in body


def gate_install_finality(functions: dict[str, str]) -> None:
    body = functions["confirm_install"]
    assert "get_installed_proposal_id() != proposal_id" in body
    assert "get_installed_candidate_hash() != proposal.candidate_code_hash" in body


def gate_target_governor(functions: dict[str, str]) -> None:
    body = functions["install_reviewed_upgrade"]
    assert "sender_address != self.sentinelx_governor" in body


def gate_duplicate(functions: dict[str, str]) -> None:
    body = functions["confirm_install"]
    assert "if candidate_hash != proposal.candidate_code_hash" in body


def gate_expiry(functions: dict[str, str]) -> None:
    body = functions["is_upgrade_authorized"]
    assert "_now() > int(proposal.execution_deadline)" in body


def gate_collision(functions: dict[str, str]) -> None:
    body = functions["create_proposal"]
    assert "active_proposal_by_target" in body


def gate_replay(functions: dict[str, str]) -> None:
    body = functions["_reserve_evidence"]
    assert "self.used_evidence_ids.get(key, False)" in body


def gate_post_verified(functions: dict[str, str]) -> None:
    body = functions["repair_evidence"]
    assert "STATUS_VERIFIED" not in body


def gate_registration_no_early_flag(functions: dict[str, str]) -> None:
    assert "self.registered_with_sentinelx = True" not in functions["register_with_sentinelx"]


def gate_governor_registration_view(functions: dict[str, str]) -> None:
    body = functions["register_with_sentinelx"]
    assert "is_target_registered" in body
    assert "self.registered_with_sentinelx" not in body


def gate_derived_registration(functions: dict[str, str]) -> None:
    body = functions["is_registered_with_sentinelx"]
    assert "is_target_registered" in body
    assert "return self.registered_with_sentinelx" not in body


def gate_target_owner_view(functions: dict[str, str]) -> None:
    assert "target_view.get_owner() != owner_address" in functions["register_target"]


def gate_target_governor_view(functions: dict[str, str]) -> None:
    assert "target_view.get_upgrade_governor() != gl.message.contract_address" in functions["register_target"]


def gate_duplicate_policy(functions: dict[str, str]) -> None:
    assert "target_address in self.policies" in functions["register_target"]


def _mutations() -> tuple[Mutation, ...]:
    governor = GOVERNOR
    target = TARGET
    no_model = None
    return (
        Mutation(1, "remove parent-source SHA verification", governor, _source(
            '        if _sha256_hex(parent_bytes) != proposal.parent_code_hash:\n            return self._capture_error(proposal, "PARENT_SOURCE_HASH_MISMATCH")\n',
            '        if False:\n            return self._capture_error(proposal, "PARENT_SOURCE_HASH_MISMATCH")\n', "parent hash"),
            _source('            if sha256_hex(parent) != proposal.parent_code_hash:\n                raise Repair("PARENT_SOURCE_HASH_MISMATCH")\n', '            if False:\n                raise Repair("PARENT_SOURCE_HASH_MISMATCH")\n', "parent hash oracle"), probe_parent_hash, gate_parent),
        Mutation(2, "remove candidate-source/frozen-byte equality verification", governor, _source(
            '        if candidate_bytes != proposal.candidate_code:\n            return self._capture_error(proposal, "CANDIDATE_BYTES_MISMATCH")\n',
            '        if False:\n            return self._capture_error(proposal, "CANDIDATE_BYTES_MISMATCH")\n', "candidate equality"),
            _source('            if sha256_hex(candidate) != proposal.candidate_code_hash or candidate != proposal.candidate_code:\n                raise Repair("CANDIDATE_BYTES_MISMATCH")\n', '            if sha256_hex(candidate) != proposal.candidate_code_hash:\n                raise Repair("CANDIDATE_BYTES_MISMATCH")\n', "candidate equality oracle"), probe_candidate_frozen, gate_candidate_equality),
        Mutation(3, "allow evidence snapshot overwrite", governor, _source(
            '        if proposal.evidence_set_hash in self.evidence_snapshots:\n            raise gl.vm.UserError("Evidence snapshot is write-once and already exists")\n',
            '        if False:\n            raise gl.vm.UserError("Evidence snapshot is write-once and already exists")\n', "snapshot write-once"),
            _source('        if proposal.evidence_identity in self.snapshots:\n            raise SentinelXError("Evidence snapshot is write-once")\n', '        if False:\n            raise SentinelXError("Evidence snapshot is write-once")\n', "snapshot write-once oracle"), probe_snapshot_write_once, gate_write_once),
        Mutation(4, "remove proposal-to-snapshot binding", governor, _source(
            '        if snapshot.proposal_id != proposal.proposal_id or snapshot.target != proposal.target:\n            return False\n',
            '        if False:\n            return False\n', "snapshot binding"),
            _source('            snapshot.proposal_id == proposal.proposal_id\n            and snapshot.target == proposal.target\n', '            True\n', "snapshot binding oracle"), probe_snapshot_binding, gate_snapshot_binding),
        Mutation(5, "make evidence identity depend on transport URL", governor, _source(
            '                "evidence-identity",\n                str(proposal.proposal_id),\n',
            '                "evidence-identity",\n                proposal.candidate_source_url,\n                str(proposal.proposal_id),\n', "transport identity"),
            _source('            "sentinelx-governor-v2", "evidence-identity", str(proposal_id), target,\n', '            "sentinelx-governor-v2", "evidence-identity", str(proposal_id), target, candidate_source_url,\n', "transport identity oracle"), probe_transport_identity, gate_transport_identity),
        Mutation(6, "permit mirror recovery with mismatching bytes", governor, _source(
            '        if _sha256_hex(candidate_bytes) != proposal.candidate_code_hash:\n            return self._capture_error(proposal, "CANDIDATE_SOURCE_HASH_MISMATCH")\n        if _sha256_hex(proposal.candidate_code) != proposal.candidate_code_hash:\n            return self._capture_error(proposal, "FROZEN_CANDIDATE_HASH_MISMATCH")\n        if candidate_bytes != proposal.candidate_code:\n            return self._capture_error(proposal, "CANDIDATE_BYTES_MISMATCH")\n',
            '        if False:\n            return self._capture_error(proposal, "CANDIDATE_SOURCE_HASH_MISMATCH")\n', "mirror bytes"),
            _source_many([
                ('            if sha256_hex(candidate) != proposal.candidate_code_hash or candidate != proposal.candidate_code:\n                raise Repair("CANDIDATE_BYTES_MISMATCH")\n', '            if False:\n                raise Repair("CANDIDATE_BYTES_MISMATCH")\n', "mirror bytes oracle"),
            ]), probe_mirror_bytes, gate_mirror),
        Mutation(7, "reintroduce gl.nondet.web.get into review_proposal", governor, _source(
            '        prompt = self._semantic_prompt(\n',
            '        gl.nondet.web.get(proposal.candidate_source_url)\n        prompt = self._semantic_prompt(\n', "review web fetch"), no_model, None, gate_no_review_fetch),
        Mutation(8, "allow review before EVIDENCE_READY", governor, _source(
            '        if proposal.status not in (STATUS_EVIDENCE_READY, STATUS_REVIEW_RETRY_REQUIRED):\n',
            '        if proposal.status not in (STATUS_PROPOSED, STATUS_EVIDENCE_READY, STATUS_REVIEW_RETRY_REQUIRED):\n', "review lifecycle"),
            _source('        if caller != policy.owner or proposal.status not in (EVIDENCE_READY, RETRY):\n', '        if caller != policy.owner or proposal.status not in (PROPOSED, EVIDENCE_READY, RETRY):\n', "review lifecycle oracle"), probe_review_before_ready, gate_review_status),
        Mutation(9, "remove CI issuer authentication", governor, _source(
            '        if obj["issuer"] != expected_issuer:\n            return "EVIDENCE_ISSUER_MISMATCH"\n',
            '        if False:\n            return "EVIDENCE_ISSUER_MISMATCH"\n', "CI issuer"),
            _source('        if value["evidence_id"] != evidence_id or value["issuer"] != issuer:\n            return "EVIDENCE_ID_OR_ISSUER"\n', '        if value["evidence_id"] != evidence_id:\n            return "EVIDENCE_ID_OR_ISSUER"\n', "CI issuer oracle"),
            lambda m: probe_ci_field(m, "issuer"), gate_ci_field("issuer")),
        Mutation(10, "remove CI target binding", governor, _source(
            '        if typing.cast(str, obj["target"]).lower() != str(proposal.target).lower():\n            return "EVIDENCE_TARGET_MISMATCH"\n',
            '        if False:\n            return "EVIDENCE_TARGET_MISMATCH"\n', "CI target"),
            _source('        if value["target"].lower() != proposal.target.lower():\n            return "EVIDENCE_TARGET_BINDING"\n', '        if False:\n            return "EVIDENCE_TARGET_BINDING"\n', "CI target oracle"),
            lambda m: probe_ci_field(m, "target"), gate_ci_field("target")),
        Mutation(11, "remove CI candidate-hash binding", governor, _source(
            '        if obj["candidate_sha256"] != proposal.candidate_code_hash:\n            return "EVIDENCE_CANDIDATE_BINDING_MISMATCH"\n',
            '        if False:\n            return "EVIDENCE_CANDIDATE_BINDING_MISMATCH"\n', "CI candidate"),
            _source('        if value["candidate_sha256"] != proposal.candidate_code_hash:\n            return "EVIDENCE_CANDIDATE_BINDING"\n', '        if False:\n            return "EVIDENCE_CANDIDATE_BINDING"\n', "CI candidate oracle"),
            lambda m: probe_ci_field(m, "candidate_sha256"), gate_ci_field("candidate_sha256")),
        Mutation(12, "remove CI policy-fingerprint binding", governor, _source(
            '        if obj["policy_fingerprint"] != proposal.policy_fingerprint:\n            return "EVIDENCE_POLICY_BINDING_MISMATCH"\n',
            '        if False:\n            return "EVIDENCE_POLICY_BINDING_MISMATCH"\n', "CI policy"),
            _source('        if value["policy_fingerprint"] != proposal.policy_fingerprint:\n            return "EVIDENCE_POLICY_BINDING"\n', '        if False:\n            return "EVIDENCE_POLICY_BINDING"\n', "CI policy oracle"),
            lambda m: probe_ci_field(m, "policy_fingerprint"), gate_ci_field("policy_fingerprint")),
        Mutation(13, "bypass evidence freshness checks", governor, _source_many([
            ('        if published > now:\n            return "EVIDENCE_FROM_FUTURE"\n', '        if False:\n            return "EVIDENCE_FROM_FUTURE"\n', "freshness future"),
            ('        if now - published > max_age:\n            return "EVIDENCE_STALE"\n', '        if False:\n            return "EVIDENCE_STALE"\n', "freshness age"),
            ('        if expires < now:\n            return "EVIDENCE_EXPIRED"\n', '        if False:\n            return "EVIDENCE_EXPIRED"\n', "freshness expiry"),
            ('        if expires < published:\n            return "EVIDENCE_EXPIRY_INVALID"\n', '        if False:\n            return "EVIDENCE_EXPIRY_INVALID"\n', "freshness order"),
        ]), _source_many([
            ('        if published > self.now or self.now - published > self.policies[proposal.target].max_age:\n            return "EVIDENCE_STALE"\n', '        if False:\n            return "EVIDENCE_STALE"\n', "freshness oracle age"),
            ('        if expires < self.now or expires < published:\n            return "EVIDENCE_EXPIRED"\n', '        if False:\n            return "EVIDENCE_EXPIRED"\n', "freshness oracle expiry"),
        ]), probe_freshness, gate_freshness),
        Mutation(14, "make REQUIRED_INDEPENDENT accept no security artifact", governor, _mutate_required_contract, _source_many([
            ('        if policy.security_attestation_mode == REQUIRED_INDEPENDENT and not security_present:\n            raise SentinelXError("Required independent security evidence is missing")\n', '        if False:\n            raise SentinelXError("Required independent security evidence is missing")\n', "required security oracle proposal"),
            ('            elif policy.security_attestation_mode == REQUIRED_INDEPENDENT:\n                raise Repair("SECURITY_REQUIRED_MISSING")\n', '            elif False:\n                raise Repair("SECURITY_REQUIRED_MISSING")\n', "required security oracle capture"),
        ]), probe_required_security, None),
        Mutation(15, "allow same-owner security publisher in REQUIRED_INDEPENDENT", governor, _source(
            '        if security_attestation_mode == SECURITY_REQUIRED_INDEPENDENT and self._raw_owner(source_prefix).lower() == self._raw_owner(security_prefix).lower():\n            raise gl.vm.UserError("Security publisher must be independent from source publisher")\n',
            '        if False:\n            raise gl.vm.UserError("Security publisher must be independent from source publisher")\n', "security independence"),
            _source('            if raw_owner(security_prefix).lower() == raw_owner(source_prefix).lower():\n                raise SentinelXError("Security publisher must be independent")\n', '            if False:\n                raise SentinelXError("Security publisher must be independent")\n', "security independence oracle"), probe_same_owner_security, gate_security_independence),
        Mutation(16, "make OPTIONAL mode falsely record independent_review=true", governor, _source(
            '        security_source = "NO_EXTERNAL_SECURITY_AUDIT_SUPPLIED"\n',
            '        security_source = "INDEPENDENT_REVIEW_PASS"\n', "optional disclaimer"),
            _source('                    if snapshot.security_present else "NO_EXTERNAL_SECURITY_AUDIT_SUPPLIED")\n', '                    if snapshot.security_present else "INDEPENDENT_REVIEW_PASS")\n', "optional disclaimer oracle"), probe_optional_disclaimer, gate_optional_disclaimer),
        Mutation(17, "permit candidate bytes/hash modification during repair", governor, _source(
            '        proposal.candidate_source_url = candidate_source_url\n',
            '        proposal.candidate_source_url = candidate_source_url\n        proposal.candidate_code = b"mutated-by-repair"\n', "repair frozen bytes"),
            _source('        proposal.candidate_source_url = candidate_source_url\n', '        proposal.candidate_source_url = candidate_source_url\n        proposal.candidate_code = b"mutated-by-repair"\n', "repair frozen bytes oracle"), probe_repair_frozen, gate_repair_frozen),
        Mutation(18, "remove one semantic-vector field from exact equality", governor, _source(
            '        if left_obj.get("result_kind") == RESULT_DECISION:\n            for key in SEMANTIC_VECTOR:\n',
            '        if left_obj.get("result_kind") == RESULT_DECISION:\n            for key in SEMANTIC_VECTOR[1:]:\n', "exact semantic vector"),
            _source('        if leader != validator:\n', '        if {key: leader[key] for key in SEMANTIC_VECTOR[1:]} != {key: validator[key] for key in SEMANTIC_VECTOR[1:]}:\n', "exact semantic vector oracle"), probe_vector_consensus, gate_vector_exact),
        Mutation(19, "approve when 13/14 fields pass", governor, _source(
            '        approved = True\n        for key in SEMANTIC_VECTOR:\n            approved = approved and checks[key]\n',
            '        approved = sum(1 for key in SEMANTIC_VECTOR if checks[key]) >= len(SEMANTIC_VECTOR) - 1\n', "semantic partial pass"),
            _source('        if not all(semantic[k] for k in SEMANTIC_VECTOR):\n', '        if sum(1 for k in SEMANTIC_VECTOR if semantic[k]) < len(SEMANTIC_VECTOR) - 1:\n', "semantic partial pass oracle"), probe_partial_vector, gate_partial_vector),
        Mutation(20, "accept malformed or extra model output", governor, _source(
            '        if not isinstance(value, dict) or len(value) != len(SEMANTIC_VECTOR):\n',
            '        if not isinstance(value, dict):\n', "exact model output"),
            _source('        if set(semantic) != set(SEMANTIC_VECTOR) or any(type(semantic[k]) is not bool for k in SEMANTIC_VECTOR):\n', '        if any(type(semantic[k]) is not bool for k in SEMANTIC_VECTOR):\n', "exact model output oracle"), probe_malformed_output, gate_exact_output),
        Mutation(21, "skip validator independent recomputation", governor, _source(
            '            validator_result = self._independent_snapshot_review(\n                proposal_memory, policy_memory, snapshot_memory, now\n            )\n            return self._same_review_result(returned.calldata, validator_result)\n',
            '            return True\n', "validator recomputation"),
            _source('        if leader != validator:\n', '        if False:\n', "validator recomputation oracle"), probe_validator_recompute, gate_validator),
        Mutation(22, "allow install before finalized authorization", governor, _source(
            '        if target_view.get_installed_proposal_id() != proposal_id:\n            raise gl.vm.UserError("Target installation is not finalized")\n        if target_view.get_installed_candidate_hash() != proposal.candidate_code_hash:\n            raise gl.vm.UserError("Finalized target hash does not match candidate")\n',
            '        if False:\n            raise gl.vm.UserError("Target installation is not finalized")\n', "install finality"), no_model, None, gate_install_finality),
        Mutation(23, "remove governor-only install authorization", target, _source(
            '        if gl.message.sender_address != self.sentinelx_governor:\n            raise gl.vm.UserError("Only SentinelX may install an upgrade")\n',
            '        if False:\n            raise gl.vm.UserError("Only SentinelX may install an upgrade")\n', "target governor authority"), no_model, None, gate_target_governor),
        Mutation(24, "allow duplicate installation/confirmation", governor, _source(
            '            if candidate_hash != proposal.candidate_code_hash:\n                raise gl.vm.UserError("Conflicting duplicate installation")\n',
            '            if False:\n                raise gl.vm.UserError("Conflicting duplicate installation")\n', "duplicate install"), no_model, None, gate_duplicate),
        Mutation(25, "allow late execution after authorization expiry", governor, _source(
            '        if self._now() > int(proposal.execution_deadline):\n            return False\n',
            '        if False:\n            return False\n', "authorization expiry"), _source(
            '        return proposal.status == QUEUED and self.now <= proposal.execution_deadline\n',
            '        return proposal.status == QUEUED\n', "authorization expiry oracle"), probe_late_authorization, gate_expiry),
        Mutation(26, "remove active-proposal collision guard", governor, _source(
            '        if self.active_proposal_by_target.get(target_address, self._empty_proposal()) != self._empty_proposal():\n            raise gl.vm.UserError("Target already has an active proposal")\n',
            '        if False:\n            raise gl.vm.UserError("Target already has an active proposal")\n', "active collision"), _source(
            '        if caller != policy.owner or self.active[target]:\n', '        if caller != policy.owner:\n', "active collision oracle"), probe_active_collision, gate_collision),
        Mutation(27, "remove global evidence-ID replay protection", governor, _source(
            '        if self.used_evidence_ids.get(key, False):\n            raise gl.vm.UserError("Evidence identifier has already been used")\n',
            '        if False:\n            raise gl.vm.UserError("Evidence identifier has already been used")\n', "global evidence replay"), _source(
            '            if len(evidence_id) < 8 or evidence_id in self.used_evidence_ids:\n', '            if len(evidence_id) < 8:\n', "global evidence replay oracle"), probe_global_replay, gate_replay),
        Mutation(28, "allow post-VERIFIED proposal mutation", governor, _source(
            '        if proposal.status not in (STATUS_EVIDENCE_REPAIR_REQUIRED, STATUS_EVIDENCE_RETRY_REQUIRED, STATUS_REVIEW_RETRY_REQUIRED):\n',
            '        if proposal.status not in (STATUS_EVIDENCE_REPAIR_REQUIRED, STATUS_EVIDENCE_RETRY_REQUIRED, STATUS_REVIEW_RETRY_REQUIRED, STATUS_VERIFIED):\n', "post verified mutation"), _source(
            '        if caller != policy.owner or proposal.status not in (REPAIR, RETRY, EVIDENCE_RETRY):\n',
            '        if caller != policy.owner or proposal.status not in (REPAIR, RETRY, EVIDENCE_RETRY, VERIFIED):\n', "post verified mutation oracle"), probe_post_verified_mutation, gate_post_verified),
        Mutation(29, "set target registered flag before child succeeds", target, _source(
            '        SentinelXGovernorInterface(self.sentinelx_governor).emit(on="finalized").register_target(\n',
            '        self.registered_with_sentinelx = True\n        SentinelXGovernorInterface(self.sentinelx_governor).emit(on="finalized").register_target(\n',
            "registration early flag"), _source(
            '        self._pending_registration = request\n',
            '        self.registered_with_sentinelx = True\n        self._pending_registration = request\n',
            "registration early flag oracle"), probe_no_early_registration_flag, gate_registration_no_early_flag),
        Mutation(30, "trust local registration flag instead of governor", target, _source(
            '        if SentinelXGovernorInterface(self.sentinelx_governor).view().is_target_registered(\n            str(gl.message.contract_address)\n        ):\n',
            '        if self.registered_with_sentinelx:\n', "registration authority"), _source(
            '        if self.governor.is_target_registered(self.target):\n',
            '        if self.registered_with_sentinelx:\n', "registration authority oracle"), probe_local_flag_authority, gate_governor_registration_view),
        Mutation(31, "block retry after failed registration child", target, _source_many([
            ('        if SentinelXGovernorInterface(self.sentinelx_governor).view().is_target_registered(\n            str(gl.message.contract_address)\n        ):\n',
             '        if self.registered_with_sentinelx or SentinelXGovernorInterface(self.sentinelx_governor).view().is_target_registered(\n            str(gl.message.contract_address)\n        ):\n', "registration retry guard"),
            ('        SentinelXGovernorInterface(self.sentinelx_governor).emit(on="finalized").register_target(\n',
             '        self.registered_with_sentinelx = True\n        SentinelXGovernorInterface(self.sentinelx_governor).emit(on="finalized").register_target(\n', "registration retry flag"),
        ]), _source_many([
            ('        if self.governor.is_target_registered(self.target):\n',
             '        if self.registered_with_sentinelx or self.governor.is_target_registered(self.target):\n', "registration retry guard oracle"),
            ('        self._pending_registration = request\n',
             '        self.registered_with_sentinelx = True\n        self._pending_registration = request\n', "registration retry flag oracle"),
        ]), probe_retry_after_registration_failure, gate_governor_registration_view),
        Mutation(32, "target derived registration returns true without governor policy", target, _source(
            '        return SentinelXGovernorInterface(self.sentinelx_governor).view().is_target_registered(\n            str(gl.message.contract_address)\n        )\n',
            '        return self.registered_with_sentinelx\n', "derived registration"), _source(
            '        return self.governor.is_target_registered(self.target)\n',
            '        return self.registered_with_sentinelx\n', "derived registration oracle"), probe_derived_registration, gate_derived_registration),
        Mutation(33, "remove governor target owner verification", governor, _source(
            '        if target_view.get_owner() != owner_address:\n            raise gl.vm.UserError("Registration owner does not match the target owner")\n',
            '        if False:\n            raise gl.vm.UserError("Registration owner does not match the target owner")\n', "target owner verification"), no_model, None, gate_target_owner_view),
        Mutation(34, "remove governor target-governor verification", governor, _source(
            '        if target_view.get_upgrade_governor() != gl.message.contract_address:\n            raise gl.vm.UserError("Target is not configured for this SentinelX governor")\n',
            '        if False:\n            raise gl.vm.UserError("Target is not configured for this SentinelX governor")\n', "target governor verification"), no_model, None, gate_target_governor_view),
        Mutation(35, "allow duplicate governor policy registration", governor, _source(
            '        if target_address in self.policies:\n            raise gl.vm.UserError("Target policy is immutable and already registered")\n',
            '        if False:\n            raise gl.vm.UserError("Target policy is immutable and already registered")\n', "duplicate policy"), _source(
            '        if target in self.policies:\n            raise SentinelXError("Target policy is immutable")\n',
            '        if False:\n            raise SentinelXError("Target policy is immutable")\n', "duplicate policy oracle"), probe_duplicate_policy_registration, gate_duplicate_policy),
    )


def _verify_frozen_sources() -> None:
    for path, expected in FROZEN_HASHES.items():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"frozen V2 source changed unexpectedly: {path} ({actual})")


def run() -> dict[str, Any]:
    _verify_frozen_sources()
    results: list[dict[str, Any]] = []
    for mutation in _mutations():
        _verify_frozen_sources()
        with tempfile.TemporaryDirectory(prefix=f"sentinelx-v2-mutant-{mutation.number}-") as name:
            temp_root = Path(name)
            try:
                contract_copy, oracle_copy = _copy_and_mutate(temp_root, mutation)
                compile(contract_copy.read_text(encoding="utf-8"), str(contract_copy), "exec")
                module: ModuleType | None = None
                if oracle_copy is not None:
                    module = _load_oracle(temp_root, mutation)
                if mutation.probe is not None:
                    if module is None:
                        raise AssertionError("behavioral mutation has no oracle copy")
                    mutation.probe(module)
                if mutation.gate is not None:
                    _ast_gate(contract_copy, mutation.gate)
                result = {"number": mutation.number, "name": mutation.name,
                          "status": "SURVIVED", "reason": "all focused checks accepted the mutant"}
            except Exception as error:
                result = {"number": mutation.number, "name": mutation.name,
                          "status": "KILLED", "reason": f"{type(error).__name__}: {error}"}
            finally:
                if module is not None:
                    _unload_oracle(module)
        _verify_frozen_sources()
        results.append(result)
    killed = sum(item["status"] == "KILLED" for item in results)
    survivors = [item for item in results if item["status"] == "SURVIVED"]
    return {
        "schema": "sentinelx-v2-mutation-result-v1",
        "mutation_count": len(results), "killed": killed,
        "surviving_mutations": survivors, "result": "PASS" if not survivors else "FAIL",
        "mutations": results,
        "frozen_sources_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit only the JSON result")
    args = parser.parse_args()
    try:
        result = run()
    except Exception as error:
        payload = {"schema": "sentinelx-v2-mutation-result-v1", "result": "BLOCKED",
                   "error": f"{type(error).__name__}: {error}"}
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for item in result["mutations"]:
            print(f"{item['status']:8} M{int(item['number']):02d} {item['name']} — {item['reason']}")
        print(f"{result['killed']}/{result['mutation_count']} mutations killed; result={result['result']}")
        if result["surviving_mutations"]:
            print("SURVIVING MUTATIONS:")
            print(json.dumps(result["surviving_mutations"], indent=2, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
