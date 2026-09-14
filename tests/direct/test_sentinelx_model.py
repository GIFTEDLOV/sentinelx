from __future__ import annotations

import json
from pathlib import Path

import pytest

from direct.sentinelx_model import (
    SEMANTIC_VECTOR,
    STATUS_CANCELLED,
    STATUS_EXECUTION_FAILED,
    STATUS_EXPIRED,
    STATUS_PROPOSED,
    STATUS_QUEUED,
    STATUS_REJECTED,
    STATUS_REPAIR,
    STATUS_RETRY,
    STATUS_VERIFIED,
    SentinelXError,
    SentinelXModel,
    ReleaseProposal,
    immutable_url,
    is_sha256,
    sha256_hex,
)


NOW = 1_700_000_000
TARGET_A = "0x" + "a" * 40
TARGET_B = "0x" + "b" * 40
OWNER_A = "0x" + "1" * 40
OWNER_B = "0x" + "2" * 40
SOURCE_AUTHORITY = "sentinelx-app"
CI_AUTHORITY = "sentinelx-ci"
SECURITY_AUTHORITY = "independent-security"
SOURCE_PREFIX = "https://raw.githubusercontent.com/sentinelx-labs/sentinelx-app/"
SOURCE_PREFIX_B = "https://raw.githubusercontent.com/sentinelx-labs/other-app/"
CI_PREFIX = "https://raw.githubusercontent.com/sentinelx-labs/sentinelx-ci/"
SECURITY_PREFIX = "https://raw.githubusercontent.com/independent-labs/sentinelx-reviews/"
SECURITY_SAME_OWNER_PREFIX = "https://raw.githubusercontent.com/sentinelx-labs/security-reviews/"
PARENT_COMMIT = "a" * 40
CANDIDATE_COMMIT = "b" * 40
REPAIRED_COMMIT = "c" * 40
CI_COMMIT = "d" * 40
SECURITY_COMMIT = "e" * 40
PARENT_URL = SOURCE_PREFIX + PARENT_COMMIT + "/contracts/protected_app_v1.py"
CANDIDATE_URL = SOURCE_PREFIX + CANDIDATE_COMMIT + "/contracts/protected_app_v2_safe.py"
REPAIRED_CANDIDATE_URL = SOURCE_PREFIX + REPAIRED_COMMIT + "/contracts/protected_app_v2_safe.py"
CI_URL = CI_PREFIX + CI_COMMIT + "/evidence/ci.json"
SECURITY_URL = SECURITY_PREFIX + SECURITY_COMMIT + "/evidence/security.json"
PARENT_BYTES = b"sentinelx parent source v1\n"
CANDIDATE_BYTES = b"sentinelx safe candidate v2\n"


def constitution() -> str:
    return json.dumps(
        {
            "version": "sentinelx-release-constitution-v1",
            "required_vector": list(SEMANTIC_VECTOR),
            "rules": [
                "preserve storage layout",
                "preserve public interface",
                "preserve user rights",
                "preserve the SentinelX authority",
                "require finalized consequences",
                "require authenticated independent evidence",
                "preserve safe fund flow",
            ],
        },
        sort_keys=True,
    )


def register(model: SentinelXModel, *, target: str = TARGET_A, owner: str = OWNER_A,
             source_prefix: str = SOURCE_PREFIX, security_prefix: str = SECURITY_PREFIX,
             current_hash: str | None = None, caller: str | None = None) -> None:
    model.register_target(
        target=target,
        owner=owner,
        project_name="SentinelX Protected App",
        constitution=constitution(),
        source_authority=SOURCE_AUTHORITY,
        ci_authority=CI_AUTHORITY,
        security_authority=SECURITY_AUTHORITY,
        source_prefix=source_prefix,
        ci_prefix=CI_PREFIX,
        security_prefix=security_prefix,
        current_version="1.0.0",
        current_source_url=source_prefix + PARENT_COMMIT + "/contracts/protected_app_v1.py",
        current_code_hash=current_hash or sha256_hex(PARENT_BYTES),
        max_age=3_600,
        proposal_ttl=7_200,
        execution_timeout=3_600,
        caller=caller or target,
    )


def create(model: SentinelXModel, *, target: str = TARGET_A, owner: str = OWNER_A,
           candidate_url: str = CANDIDATE_URL, candidate_code: bytes = CANDIDATE_BYTES,
           ci_url: str = CI_URL, ci_id: str = "ci-proof-0001",
           security_url: str = SECURITY_URL, security_id: str = "security-proof-0001",
           version: str = "2.0.0", intent: str = "safe compatible release"):
    return model.create_proposal(
        target=target,
        candidate_version=version,
        candidate_source_url=candidate_url,
        candidate_code=candidate_code,
        ci_evidence_url=ci_url,
        ci_evidence_id=ci_id,
        security_evidence_url=security_url,
        security_evidence_id=security_id,
        release_intent=intent,
        caller=owner,
    )


def valid_web(model: SentinelXModel, proposal, *, parent: bytes = PARENT_BYTES,
              candidate: bytes = CANDIDATE_BYTES, now: int = NOW,
              ci_overrides: dict | None = None, security_overrides: dict | None = None,
              ci_status: int | None = None) -> dict:
    ci = {
        "schema": "sentinelx-evidence-v1",
        "kind": "ci",
        "evidence_id": proposal.ci_evidence_id,
        "issuer": CI_AUTHORITY,
        "target": proposal.target,
        "parent_sha256": proposal.parent_code_hash,
        "candidate_sha256": proposal.candidate_code_hash,
        "policy_fingerprint": proposal.policy_fingerprint,
        "published_at": now - 30,
        "expires_at": now + 3_600,
        "checks": {
            "genvm_lint": True,
            "typecheck": True,
            "schema": True,
            "direct_tests": True,
            "adversarial_tests": True,
            "source_parity": True,
            "transaction_safety": True,
        },
    }
    security = {
        "schema": "sentinelx-evidence-v1",
        "kind": "security",
        "evidence_id": proposal.security_evidence_id,
        "issuer": SECURITY_AUTHORITY,
        "target": proposal.target,
        "parent_sha256": proposal.parent_code_hash,
        "candidate_sha256": proposal.candidate_code_hash,
        "policy_fingerprint": proposal.policy_fingerprint,
        "published_at": now - 30,
        "expires_at": now + 3_600,
        "verdict": "PASS",
        "independent_review": True,
    }
    if ci_overrides:
        ci.update(ci_overrides)
    if security_overrides:
        security.update(security_overrides)
    ci_body = json.dumps(ci).encode()
    security_body = json.dumps(security).encode()
    return {
        PARENT_URL: parent,
        proposal.candidate_source_url: candidate,
        proposal.ci_evidence_url: (ci_status, ci_body) if ci_status is not None else ci_body,
        proposal.security_evidence_url: security_body,
    }


def all_true() -> dict[str, bool]:
    return {key: True for key in SEMANTIC_VECTOR}


def one_false(key: str) -> dict[str, bool]:
    checks = all_true()
    checks[key] = False
    return checks


def prepared() -> tuple[SentinelXModel, ReleaseProposal]:
    model = SentinelXModel(NOW)
    register(model)
    proposal = create(model)
    return model, proposal


def test_valid_registration_binds_policy_and_fingerprint():
    model = SentinelXModel(NOW)
    register(model)
    policy = model.policies[TARGET_A]
    assert policy.current_code_hash == sha256_hex(PARENT_BYTES)
    assert len(policy.policy_fingerprint) == 64
    assert policy.project_name == "SentinelX Protected App"


def test_unauthorized_registration_is_rejected():
    with pytest.raises(SentinelXError, match="Only the target"):
        register(SentinelXModel(NOW), caller=OWNER_A)


def test_duplicate_registration_is_rejected():
    model = SentinelXModel(NOW)
    register(model)
    with pytest.raises(SentinelXError, match="immutable"):
        register(model)


def test_zero_or_invalid_owner_is_rejected():
    with pytest.raises(SentinelXError, match="Owner"):
        register(SentinelXModel(NOW), owner="0x" + "0" * 40)
    with pytest.raises(SentinelXError, match="Owner"):
        register(SentinelXModel(NOW), owner="not-an-address")


def test_invalid_constitution_is_rejected():
    model = SentinelXModel(NOW)
    with pytest.raises(SentinelXError, match="constitution"):
        model.register_target(
            target=TARGET_A, owner=OWNER_A, project_name="x", constitution="{}",
            source_authority=SOURCE_AUTHORITY, ci_authority=CI_AUTHORITY,
            security_authority=SECURITY_AUTHORITY, source_prefix=SOURCE_PREFIX,
            ci_prefix=CI_PREFIX, security_prefix=SECURITY_PREFIX,
            current_version="1.0.0", current_source_url=PARENT_URL,
            current_code_hash=sha256_hex(PARENT_BYTES), caller=TARGET_A,
        )


def test_duplicate_authorities_are_rejected():
    model = SentinelXModel(NOW)
    with pytest.raises(SentinelXError, match="Authorities"):
        model.register_target(
            target=TARGET_A, owner=OWNER_A, project_name="x", constitution=constitution(),
            source_authority="same", ci_authority="same", security_authority=SECURITY_AUTHORITY,
            source_prefix=SOURCE_PREFIX, ci_prefix=CI_PREFIX, security_prefix=SECURITY_PREFIX,
            current_version="1.0.0", current_source_url=PARENT_URL,
            current_code_hash=sha256_hex(PARENT_BYTES), caller=TARGET_A,
        )


def test_security_publisher_must_be_independent():
    with pytest.raises(SentinelXError, match="independent"):
        register(SentinelXModel(NOW), security_prefix=SECURITY_SAME_OWNER_PREFIX)


def test_malformed_source_urls_are_rejected():
    assert not immutable_url("http://raw.githubusercontent.com/a/b/" + PARENT_COMMIT + "/x", SOURCE_PREFIX)
    assert not immutable_url(SOURCE_PREFIX + PARENT_COMMIT + "/", SOURCE_PREFIX)
    assert not immutable_url(SOURCE_PREFIX + "z" * 40 + "/contracts/x.py", SOURCE_PREFIX)


def test_branch_url_is_rejected():
    model = SentinelXModel(NOW)
    register(model)
    with pytest.raises(SentinelXError, match="immutable"):
        create(model, candidate_url=SOURCE_PREFIX + "main/contracts/protected_app_v2_safe.py")


@pytest.mark.parametrize("suffix", ["../x", "./x", "%2e%2e/x", "contracts\\x.py", "contracts//x.py", "contracts/x.py?ref=main"])
def test_path_traversal_and_aliases_are_rejected(suffix):
    model = SentinelXModel(NOW)
    register(model)
    with pytest.raises(SentinelXError, match="immutable"):
        create(model, candidate_url=SOURCE_PREFIX + CANDIDATE_COMMIT + "/" + suffix)


def test_invalid_parent_hash_is_rejected_at_registration():
    with pytest.raises(SentinelXError, match="SHA-256"):
        register(SentinelXModel(NOW), current_hash="g" * 64)


def test_invalid_candidate_hash_is_detected_if_frozen_state_is_tampered():
    model, proposal = prepared()
    proposal.candidate_code_hash = "f" * 64
    status = model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=all_true(), caller=OWNER_A)
    assert status == STATUS_REPAIR
    assert proposal.last_review_code == "CANDIDATE_SOURCE_HASH_MISMATCH"


def test_duplicate_evidence_ids_are_rejected():
    model = SentinelXModel(NOW)
    register(model)
    with pytest.raises(SentinelXError, match="distinct"):
        create(model, ci_id="same-proof-01", security_id="same-proof-01")


def test_evidence_ids_cannot_cross_target_replay():
    model = SentinelXModel(NOW)
    register(model, target=TARGET_A, owner=OWNER_A)
    create(model, target=TARGET_A, owner=OWNER_A)
    register(model, target=TARGET_B, owner=OWNER_B, source_prefix=SOURCE_PREFIX_B,
             security_prefix="https://raw.githubusercontent.com/independent-labs/other-reviews/")
    with pytest.raises(SentinelXError, match="already been used"):
        create(model, target=TARGET_B, owner=OWNER_B, candidate_url=SOURCE_PREFIX_B + CANDIDATE_COMMIT + "/contracts/v2.py",
               ci_url=CI_PREFIX + "f" * 40 + "/evidence/ci-b.json",
               security_url="https://raw.githubusercontent.com/independent-labs/other-reviews/" + "1" * 40 + "/evidence/security-b.json")


def test_evidence_ids_are_global_across_ci_and_security_kinds():
    model = SentinelXModel(NOW)
    register(model, target=TARGET_A, owner=OWNER_A)
    create(model, target=TARGET_A, owner=OWNER_A)
    register(model, target=TARGET_B, owner=OWNER_B, source_prefix=SOURCE_PREFIX_B,
             security_prefix="https://raw.githubusercontent.com/independent-labs/other-reviews/")
    with pytest.raises(SentinelXError, match="already been used"):
        create(model, target=TARGET_B, owner=OWNER_B,
               candidate_url=SOURCE_PREFIX_B + CANDIDATE_COMMIT + "/contracts/v2.py",
               ci_url=CI_PREFIX + "f" * 40 + "/evidence/ci-b.json", ci_id="ci-proof-0002",
               security_url="https://raw.githubusercontent.com/independent-labs/other-reviews/" + "1" * 40 + "/evidence/security-b.json",
               security_id="ci-proof-0001")


def test_stale_evidence_is_repairable():
    model, proposal = prepared()
    web = valid_web(model, proposal, now=NOW - 4_000)
    assert model.review(proposal.proposal_id, web=web, semantic=all_true(), caller=OWNER_A) == STATUS_REPAIR
    assert proposal.last_review_code == "EVIDENCE_STALE"


def test_expired_evidence_is_repairable():
    model, proposal = prepared()
    web = valid_web(model, proposal, security_overrides={"expires_at": NOW - 1})
    assert model.review(proposal.proposal_id, web=web, semantic=all_true(), caller=OWNER_A) == STATUS_REPAIR
    assert proposal.last_review_code == "EVIDENCE_EXPIRED"


def test_future_evidence_is_repairable():
    model, proposal = prepared()
    web = valid_web(model, proposal, ci_overrides={"published_at": NOW + 1})
    assert model.review(proposal.proposal_id, web=web, semantic=all_true(), caller=OWNER_A) == STATUS_REPAIR
    assert proposal.last_review_code == "EVIDENCE_FROM_FUTURE"


def test_malformed_evidence_is_repairable():
    model, proposal = prepared()
    web = valid_web(model, proposal)
    web[proposal.ci_evidence_url] = b"not-json"
    assert model.review(proposal.proposal_id, web=web, semantic=all_true(), caller=OWNER_A) == STATUS_REPAIR
    assert proposal.last_review_code == "EVIDENCE_JSON_INVALID"


def test_wrong_issuer_target_policy_and_hash_bindings_fail_closed():
    cases = [
        ({"issuer": "attacker"}, "EVIDENCE_ID_OR_ISSUER"),
        ({"target": TARGET_B}, "EVIDENCE_TARGET_BINDING"),
        ({"policy_fingerprint": "0" * 64}, "EVIDENCE_POLICY_BINDING"),
        ({"parent_sha256": "0" * 64}, "EVIDENCE_PARENT_BINDING"),
        ({"candidate_sha256": "0" * 64}, "EVIDENCE_CANDIDATE_BINDING"),
    ]
    for override, expected in cases:
        model, proposal = prepared()
        web = valid_web(model, proposal, ci_overrides=override)
        assert model.review(proposal.proposal_id, web=web, semantic=all_true(), caller=OWNER_A) == STATUS_REPAIR
        assert proposal.last_review_code == expected


def test_candidate_replay_is_blocked_after_verified_install():
    model, proposal = prepared()
    assert model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=all_true(), caller=OWNER_A) == STATUS_QUEUED
    model.confirm_install(proposal.proposal_id, sender=TARGET_A, candidate_hash=proposal.candidate_code_hash,
                          installed_proposal_id=proposal.proposal_id, installed_hash=proposal.candidate_code_hash)
    assert proposal.status == STATUS_VERIFIED
    with pytest.raises(SentinelXError, match="already been installed"):
        create(model, version="3.0.0", ci_id="ci-proof-0002", security_id="security-proof-0002")


def test_active_proposal_collision_is_rejected():
    model, proposal = prepared()
    with pytest.raises(SentinelXError, match="active"):
        create(model, version="2.0.1", ci_id="ci-proof-0002", security_id="security-proof-0002")
    assert proposal.status == STATUS_PROPOSED


def test_candidate_equal_to_current_code_is_rejected():
    model = SentinelXModel(NOW)
    register(model)
    with pytest.raises(SentinelXError, match="equals"):
        create(model, candidate_code=PARENT_BYTES, ci_id="ci-proof-0011", security_id="security-proof-0011")


def test_safe_candidate_is_accepted_by_all_true_vector():
    model, proposal = prepared()
    assert model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=all_true(), caller=OWNER_A) == STATUS_QUEUED
    assert model.authorized(proposal.proposal_id, target=TARGET_A, candidate_hash=proposal.candidate_code_hash)


@pytest.mark.parametrize("unsafe_field", [
    "no_privilege_escalation",
    "upgrade_authority_preserved",
    "fund_flow_safe",
    "storage_layout_compatible",
    "behavioral_scope_matches_release",
])
def test_unsafe_candidate_vector_field_rejects_without_threshold(unsafe_field):
    model, proposal = prepared()
    assert model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=one_false(unsafe_field), caller=OWNER_A) == STATUS_REJECTED
    assert model.active[TARGET_A] == 0


def test_all_fourteen_vector_fields_are_required():
    assert len(SEMANTIC_VECTOR) == 14
    model, proposal = prepared()
    incomplete = all_true()
    incomplete.pop("fund_flow_safe")
    assert model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=incomplete, caller=OWNER_A) == STATUS_RETRY


def test_reasoning_text_cannot_authorize():
    model, proposal = prepared()
    checks = all_true()
    checks["reasoning"] = "looks safe"  # type: ignore[index]
    assert model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=checks, caller=OWNER_A) == STATUS_RETRY


def test_evidence_repair_freezes_candidate_parent_and_policy():
    model, proposal = prepared()
    web = valid_web(model, proposal)
    web[proposal.candidate_source_url] = b"tampered"
    model.review(proposal.proposal_id, web=web, semantic=all_true(), caller=OWNER_A)
    old = (proposal.target, proposal.parent_code_hash, proposal.candidate_code, proposal.candidate_code_hash, proposal.policy_fingerprint)
    model.repair_evidence(
        proposal.proposal_id,
        candidate_source_url=REPAIRED_CANDIDATE_URL,
        ci_evidence_url=CI_PREFIX + "f" * 40 + "/evidence/ci-repaired.json",
        ci_evidence_id="ci-repaired-0001",
        security_evidence_url=SECURITY_PREFIX + "1" * 40 + "/evidence/security-repaired.json",
        security_evidence_id="security-repaired-0001",
        caller=OWNER_A,
    )
    assert (proposal.target, proposal.parent_code_hash, proposal.candidate_code, proposal.candidate_code_hash, proposal.policy_fingerprint) == old
    assert proposal.status == STATUS_PROPOSED


def test_transient_fetch_failure_is_retryable_not_rejection():
    model, proposal = prepared()
    web = valid_web(model, proposal, ci_status=503)
    assert model.review(proposal.proposal_id, web=web, semantic=all_true(), caller=OWNER_A) == STATUS_RETRY
    assert proposal.status != STATUS_REJECTED


def test_retry_review_reprocesses_same_frozen_candidate():
    model, proposal = prepared()
    model.review(proposal.proposal_id, web=valid_web(model, proposal, ci_status=503), semantic=all_true(), caller=OWNER_A)
    model.retry_review(proposal.proposal_id, web=valid_web(model, proposal), semantic=all_true(), caller=OWNER_A)
    assert proposal.status == STATUS_QUEUED
    assert proposal.candidate_code == CANDIDATE_BYTES


def test_cancellation_releases_active_slot_but_does_not_release_evidence_ids():
    model, proposal = prepared()
    model.cancel(proposal.proposal_id, caller=OWNER_A)
    assert proposal.status == STATUS_CANCELLED and model.active[TARGET_A] == 0
    with pytest.raises(SentinelXError, match="already been used"):
        create(model, version="2.0.1", ci_id=proposal.ci_evidence_id, security_id=proposal.security_evidence_id)


def test_expiration_releases_proposed_slot():
    model, proposal = prepared()
    model.now = proposal.expires_at + 1
    model.expire(proposal.proposal_id)
    assert proposal.status == STATUS_EXPIRED and model.active[TARGET_A] == 0


def test_successful_install_confirmation_updates_policy_and_history():
    model, proposal = prepared()
    model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=all_true(), caller=OWNER_A)
    model.confirm_install(proposal.proposal_id, sender=TARGET_A, candidate_hash=proposal.candidate_code_hash,
                          installed_proposal_id=proposal.proposal_id, installed_hash=proposal.candidate_code_hash)
    assert proposal.status == STATUS_VERIFIED
    assert model.policies[TARGET_A].current_version == "2.0.0"
    assert model.policies[TARGET_A].current_code_hash == sha256_hex(CANDIDATE_BYTES)
    assert model.history[TARGET_A] == [proposal.proposal_id]


def test_reconciliation_proves_finalized_install_without_rebroadcast():
    model, proposal = prepared()
    model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=all_true(), caller=OWNER_A)
    model.reconcile(proposal.proposal_id, caller=OWNER_A, installed_proposal_id=proposal.proposal_id,
                    installed_hash=proposal.candidate_code_hash)
    assert proposal.status == STATUS_VERIFIED


def test_duplicate_installation_confirmation_is_idempotent_only_when_exact():
    model, proposal = prepared()
    model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=all_true(), caller=OWNER_A)
    model.confirm_install(proposal.proposal_id, sender=TARGET_A,
                          candidate_hash=proposal.candidate_code_hash,
                          installed_proposal_id=proposal.proposal_id,
                          installed_hash=proposal.candidate_code_hash)
    model.confirm_install(proposal.proposal_id, sender=TARGET_A,
                          candidate_hash=proposal.candidate_code_hash,
                          installed_proposal_id=proposal.proposal_id,
                          installed_hash=proposal.candidate_code_hash)
    with pytest.raises(SentinelXError, match="Conflicting"):
        model.confirm_install(proposal.proposal_id, sender=TARGET_A, candidate_hash="0" * 64,
                              installed_proposal_id=proposal.proposal_id, installed_hash="0" * 64)


def test_execution_timeout_marks_failure_only_from_known_parent_state():
    model, proposal = prepared()
    model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=all_true(), caller=OWNER_A)
    model.now = proposal.execution_deadline + 1
    assert model.timeout(proposal.proposal_id, installed_proposal_id=0,
                         installed_hash=model.policies[TARGET_A].current_code_hash) == STATUS_EXECUTION_FAILED
    assert model.active[TARGET_A] == 0


def test_execution_timeout_reconciles_exact_late_finalized_install():
    model, proposal = prepared()
    model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=all_true(), caller=OWNER_A)
    model.now = proposal.execution_deadline + 1
    assert model.timeout(proposal.proposal_id, installed_proposal_id=proposal.proposal_id,
                         installed_hash=proposal.candidate_code_hash) == STATUS_VERIFIED


def test_late_child_cannot_install_after_timeout():
    model, proposal = prepared()
    model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=all_true(), caller=OWNER_A)
    model.now = proposal.execution_deadline + 1
    model.timeout(proposal.proposal_id, installed_proposal_id=0,
                  installed_hash=model.policies[TARGET_A].current_code_hash)
    assert not model.authorized(proposal.proposal_id, target=TARGET_A, candidate_hash=proposal.candidate_code_hash)
    with pytest.raises(SentinelXError):
        model.confirm_install(proposal.proposal_id, sender=TARGET_A, candidate_hash=proposal.candidate_code_hash,
                              installed_proposal_id=proposal.proposal_id, installed_hash=proposal.candidate_code_hash)


def test_wrong_post_install_candidate_hash_is_rejected():
    model, proposal = prepared()
    model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=all_true(), caller=OWNER_A)
    with pytest.raises(SentinelXError, match="match"):
        model.confirm_install(proposal.proposal_id, sender=TARGET_A, candidate_hash="0" * 64,
                              installed_proposal_id=proposal.proposal_id, installed_hash="0" * 64)


def test_authorization_expires_at_execution_deadline():
    model, proposal = prepared()
    model.review(proposal.proposal_id, web=valid_web(model, proposal), semantic=all_true(), caller=OWNER_A)
    model.now = proposal.execution_deadline + 1
    assert not model.authorized(proposal.proposal_id, target=TARGET_A, candidate_hash=proposal.candidate_code_hash)


def test_source_and_candidate_bytes_are_exactly_hash_bound():
    assert is_sha256(sha256_hex(CANDIDATE_BYTES))
    assert not is_sha256("A" * 64)
    model, proposal = prepared()
    assert proposal.candidate_code_hash == sha256_hex(proposal.candidate_code)


def test_safe_and_unsafe_reference_files_are_present_and_distinct():
    safe = Path("contracts/protected_app_v2_safe.py").read_bytes()
    unsafe = Path("contracts/protected_app_v2_unsafe.py").read_bytes()
    assert safe != unsafe
    assert b"owner_replace_code" not in safe
    assert b"owner_replace_code" in unsafe
