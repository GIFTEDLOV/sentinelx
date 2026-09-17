from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_security_review_packet import build_packet
from scripts.generate_ci_evidence import make_ci_evidence
from scripts.inject_security_authority import inject
from scripts.transaction_journal import JournalError, TransactionJournal
from scripts.fee_aware_transaction import (
    estimate_fee_aware_options,
    load_fee_profile,
    profile_entry_to_estimate_options,
)
from scripts.studio_dev_lifecycle import inspect_lifecycle, reconcile_genlayer
from scripts.studio_dev_managed_bridge import MESSAGE_PRODUCING_METHODS, _capture_cli_estimate
from scripts.build_fee_profile import _journal_observations


PROFILE_ENTRY = {
    "leaderTimeunitsAllocation": "100",
    "validatorTimeunitsAllocation": "200",
    "executionBudgetPerRound": "500000",
    "totalMessageFees": "0",
    "rotationsPerRound": "3",
}
SOURCE_PREFIX = "https://raw.githubusercontent.com/GIFTEDLOV/sentinelx/"
CI_PREFIX = "https://raw.githubusercontent.com/GIFTEDLOV/sentinelx-ci/"
COMMIT_A = "a" * 40
COMMIT_B = "b" * 40


def test_message_producing_methods_never_use_generic_zero_message_fallback():
    assert {
        "register_with_sentinelx", "execute_reviewed_upgrade",
        "install_reviewed_upgrade", "confirm_install",
    } <= MESSAGE_PRODUCING_METHODS
    assert "review_proposal" not in MESSAGE_PRODUCING_METHODS
    assert "capture_evidence" not in MESSAGE_PRODUCING_METHODS


def test_capture_fallback_uses_measured_recommendation_with_headroom_and_no_messages():
    class RequoteClient:
        def __init__(self):
            self.seen = None

        def estimate_transaction_fees(self, distribution):
            self.seen = distribution
            return {"distribution": distribution, "feeValue": "123"}

    client = RequoteClient()
    result = _capture_cli_estimate(
        client=client, address="0x" + "1" * 40, args=[1], estimate={
            "distribution": {
                "leaderTimeunitsAllocation": "100",
                "validatorTimeunitsAllocation": "200",
                "executionBudgetPerRound": "156065700000000",
                "totalMessageFees": "0",
                "rotations": ["3"],
            },
            "feeValue": "624262800010352",
            "observed": {"recommendedExecutionBudgetPerRound": "193076100000000"},
        },
    )
    assert client.seen is not None
    assert client.seen["executionBudgetPerRound"] == 241345125000000
    assert result["estimation_path"] == "cli_exact_write_recommended_execution_headroom_1_25"
    assert result["distribution"]["totalMessageFees"] == "0"


class Estimator:
    def __init__(self, result: dict[str, object]):
        self.result = result

    def estimate_transaction_fees(self, request: dict[str, object]) -> dict[str, object]:
        if "appealRounds" in request:
            assert request["appealRounds"] == 1
        return self.result


def test_fee_estimate_requires_current_v06_wire_names():
    result = {"distribution": {"rotations": [1, 2]}, "feeValue": "99"}
    options = estimate_fee_aware_options(Estimator(result), {"appealRounds": 1})
    assert options.as_sdk_fees() == result
    with pytest.raises(ValueError, match="legacy"):
        estimate_fee_aware_options(
            Estimator({"FeesDistribution": {}, "feeValue": "99"}), {}
        )


def test_measured_profile_is_loaded_and_converted_without_defaults(tmp_path: Path):
    methods = {
        name: dict(PROFILE_ENTRY)
        for name in (
            "register_with_sentinelx", "create_proposal", "review_proposal",
            "install_reviewed_upgrade", "confirm_install", "reconcile_install",
        )
    }
    path = tmp_path / "fee-profile.json"
    path.write_text(json.dumps({
        "version": 1, "network": "studio_devnet", "chainId": 61997,
        "measuredAt": "2026-01-01T00:00:00Z", "deploy": PROFILE_ENTRY,
        "methods": methods,
    }), encoding="utf-8")
    loaded = load_fee_profile(path, required_methods=tuple(methods))
    converted = profile_entry_to_estimate_options(loaded["deploy"], appeal_rounds=1)  # type: ignore[arg-type]
    assert converted["rotations"] == [3, 3]
    assert converted["appealRounds"] == 1


def test_journal_reservation_blocks_duplicate_and_persists_hash_before_polling(tmp_path: Path):
    journal = TransactionJournal(tmp_path / "journal.json")
    journal.reserve_broadcast("deploy-governor", source="local")
    journal.record_submission("deploy-governor", "0x" + "a" * 64)
    assert journal.load()["operations"]["deploy-governor"]["tx_hash"] == "0x" + "a" * 64
    with pytest.raises(JournalError, match="already reserved"):
        journal.reserve_broadcast("deploy-governor")
    with pytest.raises(JournalError, match="already journaled"):
        journal.reserve_broadcast("other")
        journal.record_submission("other", "0x" + "a" * 64)


def test_journal_closes_only_verified_no_hash_attempt_and_preserves_retry_barrier(tmp_path: Path):
    journal = TransactionJournal(tmp_path / "journal.json")
    journal.reserve_broadcast("malformed-attempt")
    journal.update("malformed-attempt", state="BROADCAST_CALL_RAISED", cli_exit_code=1)
    record = journal.mark_not_broadcast(
        "malformed-attempt", latest_nonce=17, pending_nonce=17,
        verification="RPC latest/pending nonce converged after CLI returned no hash",
    )
    assert record["state"] == "BLOCKED_BEFORE_BROADCAST"
    assert record["broadcast_verified_absent"] is True
    assert journal.load()["operations"]["malformed-attempt"].get("tx_hash") is None
    with pytest.raises(JournalError, match="already reserved"):
        journal.reserve_broadcast("malformed-attempt")
    journal.reserve_broadcast("malformed-attempt.retry")


def test_journal_refuses_no_hash_close_without_nonce_convergence(tmp_path: Path):
    journal = TransactionJournal(tmp_path / "journal.json")
    journal.reserve_broadcast("ambiguous-attempt")
    journal.update("ambiguous-attempt", state="BROADCAST_CALL_RAISED")
    with pytest.raises(JournalError, match="nonce convergence"):
        journal.mark_not_broadcast(
            "ambiguous-attempt", latest_nonce=17, pending_nonce=18,
            verification="insufficient",
        )


def test_corrupt_journal_fails_closed(tmp_path: Path):
    path = tmp_path / "journal.json"
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(JournalError, match="unreadable"):
        TransactionJournal(path).load()


def test_fee_profile_parser_accepts_only_finalized_successful_observations(tmp_path: Path):
    path = tmp_path / "profile-journal.json"
    receipt = {"data": {"fee_accounting": {"fees_distribution": {"rotations": [3]}}}}
    path.write_text(json.dumps({
        "schema": "sentinelx-transaction-journal-v1",
        "operations": {
            "deploy": {
                "state": "FINALIZED_EXECUTED",
                "lifecycle": {"stored_status": "Finalized"},
                "execution_result": "FINISHED_WITH_RETURN",
                "fee_observation_kind": "deploy",
                "contract_name": "protected_app_v1",
                "receipt": receipt,
            },
            "failed": {
                "state": "FINALIZED_EXECUTION_FAILED",
                "lifecycle": {"stored_status": "Finalized"},
                "execution_result": "FINISHED_WITH_ERROR",
                "fee_observation_kind": "method",
                "method": "not-measured",
                "receipt": receipt,
            },
            "accepted": {
                "state": "SUBMITTED",
                "lifecycle": {"stored_status": "Accepted"},
                "execution_result": None,
                "fee_observation_kind": "method",
                "method": "not-measured",
                "receipt": receipt,
            },
        },
    }), encoding="utf-8")
    observations, deploys, methods = _journal_observations(path)
    assert len(observations) == 1
    assert deploys == ["protected_app_v1"]
    assert methods == []


def test_security_packet_contains_exact_bytes_hashes_diff_and_required_schema(tmp_path: Path):
    parent = tmp_path / "parent.py"
    candidate = tmp_path / "candidate.py"
    constitution = Path("deploy/release-constitution.json")
    parent.write_bytes(b"old\n")
    candidate.write_bytes(b"new\n")
    output = tmp_path / "packet"
    packet = build_packet(
        parent=parent, candidate=candidate, constitution_file=constitution,
        release_intent="safe compatible release", output_dir=output,
    )
    assert packet["publishable"] is False
    assert packet["parent_sha256"] == hashlib.sha256(b"old\n").hexdigest()
    schema = json.loads((output / "required-security-evidence-schema.json").read_text())
    assert schema["schema"] == "sentinelx-evidence-v1"
    assert schema["kind"] == "security"
    assert schema["independent_review"] is True
    assert "new" in (output / "semantic.diff").read_text()


def test_security_authority_injection_requires_different_raw_github_owner(tmp_path: Path):
    template = {
        "source_authority": "GIFTEDLOV/sentinelx",
        "ci_authority": "GIFTEDLOV/sentinelx-ci",
        "source_prefix": SOURCE_PREFIX,
        "ci_prefix": CI_PREFIX,
        "security_authority": "<<INDEPENDENT_SECURITY_AUTHORITY>>",
        "security_prefix": "<<INDEPENDENT_SECURITY_RAW_PREFIX>>",
    }
    source = tmp_path / "template.json"
    same_owner = tmp_path / "same-owner.json"
    source.write_text(json.dumps(template), encoding="utf-8")
    with pytest.raises(ValueError, match="owner"):
        inject(
            input_path=source, output_path=same_owner,
            security_authority="GIFTEDLOV/reviewer",
            security_prefix="https://raw.githubusercontent.com/GIFTEDLOV/reviewer/",
        )
    output = tmp_path / "independent.json"
    result = inject(
        input_path=source, output_path=output,
        security_authority="IndependentOrg/reviewer",
        security_prefix="https://raw.githubusercontent.com/IndependentOrg/reviewer/",
    )
    assert result["security_authority"] == "IndependentOrg/reviewer"


def test_ci_generator_emits_only_explicit_complete_envelope(tmp_path: Path, monkeypatch):
    parent = tmp_path / "parent.py"
    candidate = tmp_path / "candidate.py"
    parent.write_bytes(b"parent")
    candidate.write_bytes(b"candidate")
    monkeypatch.setattr(
        "scripts.generate_ci_evidence.run_deterministic_gates",
        lambda: {
            "genvm_lint": True, "typecheck": True, "schema": True,
            "direct_tests": True, "adversarial_tests": True,
            "source_parity": True, "transaction_safety": True,
        },
    )
    envelope = make_ci_evidence(
        target="0x" + "1" * 40,
        issuer="GIFTEDLOV/sentinelx-ci",
        evidence_id="ci-proof-2026-0001",
        parent=parent,
        candidate=candidate,
        parent_source_url=SOURCE_PREFIX + COMMIT_A + "/contracts/protected_app_v1.py",
        candidate_source_url=SOURCE_PREFIX + COMMIT_B + "/contracts/protected_app_v2_safe.py",
        source_prefix=SOURCE_PREFIX,
        ci_prefix=CI_PREFIX,
        policy_fingerprint="c" * 64,
        published_at=1_700_000_000,
        expires_at=1_700_003_600,
    )
    assert envelope["kind"] == "ci"
    checks = envelope["checks"]
    assert isinstance(checks, dict)
    assert set(checks) == {
        "genvm_lint", "typecheck", "schema", "direct_tests",
        "adversarial_tests", "source_parity", "transaction_safety",
    }
    assert envelope["candidate_sha256"] == hashlib.sha256(b"candidate").hexdigest()


def test_reconciliation_marks_polling_failure_and_never_rebroadcasts(tmp_path: Path):
    journal = TransactionJournal(tmp_path / "journal.json")
    journal.reserve_broadcast("review")
    journal.record_submission("review", "0x" + "d" * 64)

    class PollingFailureClient:
        def wait_for_transaction_receipt(self, *args, **kwargs):
            raise TimeoutError("polling timeout")

    with pytest.raises(TimeoutError):
        reconcile_genlayer(client=PollingFailureClient(), journal=journal, operation="review")
    assert journal.load()["operations"]["review"]["state"] == "POLLING_ERROR"
    with pytest.raises(JournalError, match="already reserved"):
        journal.reserve_broadcast("review")


def test_reconciliation_requires_finalized_finished_with_return_and_reads_children(tmp_path: Path):
    journal = TransactionJournal(tmp_path / "journal.json")
    journal.reserve_broadcast("registration")
    journal.record_submission("registration", "0x" + "e" * 64)

    class SuccessfulClient:
        def wait_for_transaction_receipt(self, *args, **kwargs):
            return {
                "lifecycle": {"state": "finalized"},
                "tx_execution_result_name": "FINISHED_WITH_RETURN",
            }

        def get_transaction_lifecycle(self, *args, **kwargs):
            return {
                "stored_status_name": "Finalized",
                "projected_status_name": "Finalized",
                "resolution_action_name": "NoOp",
                "decision_id": None,
                "decision_active": False,
                "evaluated_at": 1_700_000_000,
            }

        def get_triggered_transaction_ids(self, *args, **kwargs):
            return []

    receipt, record = reconcile_genlayer(
        client=SuccessfulClient(), journal=journal, operation="registration"
    )
    assert receipt["tx_execution_result_name"] == "FINISHED_WITH_RETURN"
    assert record["state"] == "FINALIZED_EXECUTED"


def test_finalize_action_requires_active_decision_identity():
    class LifecycleClient:
        def get_transaction_lifecycle(self, tx_hash):
            return {
                "stored_status_name": "Accepted",
                "projected_status_name": "Accepted",
                "resolution_action_name": "Finalize",
                "decision_id": "17",
                "decision_active": True,
                "evaluated_at": 1_700_000_000,
            }

    assert inspect_lifecycle(LifecycleClient(), "0x" + "f" * 64)["decision_id"] == "17"
