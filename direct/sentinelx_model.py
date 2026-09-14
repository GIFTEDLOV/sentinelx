"""Deterministic SentinelX lifecycle model for Direct Mode tests.

The model mirrors the contract invariants without importing the GenLayer SDK.
It is intentionally strict and is used to exercise adversarial inputs quickly;
the contract files remain the deployment source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any


SEMANTIC_VECTOR = (
    "storage_layout_compatible",
    "public_interface_compatible",
    "user_rights_preserved",
    "no_privilege_escalation",
    "upgrade_authority_preserved",
    "consensus_integrity_preserved",
    "finality_safety_preserved",
    "evidence_trust_preserved",
    "fund_flow_safe",
    "external_fetch_surface_safe",
    "liveness_preserved",
    "behavioral_scope_matches_release",
    "migration_safety_preserved",
    "constitution_satisfied",
)
STATUS_PROPOSED = "PROPOSED"
STATUS_REPAIR = "EVIDENCE_REPAIR_REQUIRED"
STATUS_RETRY = "REVIEW_RETRY_REQUIRED"
STATUS_REJECTED = "REJECTED"
STATUS_QUEUED = "UPGRADE_QUEUED"
STATUS_VERIFIED = "VERIFIED"
STATUS_EXPIRED = "EXPIRED"
STATUS_CANCELLED = "CANCELLED"
STATUS_EXECUTION_FAILED = "EXECUTION_FAILED"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_parts(*parts: str) -> str:
    return sha256_hex("\x1f".join(parts).encode())


def is_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", value))


def raw_owner(prefix: str) -> str:
    base = "https://raw.githubusercontent.com/"
    if not prefix.startswith(base) or not prefix.endswith("/"):
        return ""
    if not prefix.isascii() or "//" in prefix[len("https://") :] or "\\" in prefix or "%" in prefix:
        return ""
    pieces = prefix[len(base) :].split("/")
    if len(pieces) != 3 or pieces[2] != "":
        return ""
    if not all(re.fullmatch(r"[A-Za-z0-9._-]+", p) for p in pieces[:2]):
        return ""
    return pieces[0]


def immutable_url(url: str, prefix: str) -> bool:
    if not url.isascii() or len(url.encode()) > 1024:
        return False
    if not raw_owner(prefix) or not url.startswith(prefix):
        return False
    if any(token in url[len("https://") :] for token in ("//",)) or any(token in url for token in ("\\", "?", "#", "%")):
        return False
    pieces = url[len(prefix) :].split("/")
    if len(pieces) < 2 or not re.fullmatch(r"[0-9a-f]{40}", pieces[0]):
        return False
    return all(
        bool(part)
        and part not in (".", "..")
        and ".." not in part
        and bool(re.fullmatch(r"[A-Za-z0-9._-]+", part))
        for part in pieces[1:]
    )


def constitution_valid(value: str) -> bool:
    if not value.isascii() or not 128 <= len(value.encode()) <= 32_000:
        return False
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return False
    return (
        isinstance(parsed, dict)
        and parsed.get("version") == "sentinelx-release-constitution-v1"
        and parsed.get("required_vector") == list(SEMANTIC_VECTOR)
        and isinstance(parsed.get("rules"), list)
        and len(parsed["rules"]) >= 6
    )


@dataclass(frozen=True)
class TargetPolicy:
    owner: str
    target: str
    project_name: str
    release_constitution: str
    policy_fingerprint: str
    source_authority: str
    ci_authority: str
    security_authority: str
    source_prefix: str
    ci_prefix: str
    security_prefix: str
    current_version: str
    current_source_url: str
    current_code_hash: str
    max_evidence_age_seconds: int
    proposal_ttl_seconds: int
    execution_timeout_seconds: int
    active: bool = True


@dataclass
class ReleaseProposal:
    proposal_id: int
    target: str
    proposer: str
    parent_version: str
    parent_source_url: str
    parent_code_hash: str
    candidate_version: str
    candidate_source_url: str
    candidate_code: bytes
    candidate_code_hash: str
    ci_evidence_url: str
    ci_evidence_id: str
    security_evidence_url: str
    security_evidence_id: str
    evidence_set_hash: str
    policy_fingerprint: str
    release_intent: str
    created_at: int
    expires_at: int
    reviewed_at: int = 0
    execution_deadline: int = 0
    status: str = STATUS_PROPOSED
    last_review_code: str = ""


class SentinelXError(ValueError):
    pass


class SentinelXModel:
    def __init__(self, now: int = 1_700_000_000):
        self.now = now
        self.policies: dict[str, TargetPolicy] = {}
        self.proposals: dict[int, ReleaseProposal] = {}
        self.active: dict[str, int] = {}
        self.target_proposals: dict[str, list[int]] = {}
        self.history: dict[str, list[int]] = {}
        self.used_evidence_ids: set[str] = set()
        self.installed: set[tuple[str, str]] = set()
        self.next_id = 1

    def register_target(self, *, target: str, owner: str, project_name: str, constitution: str,
                        source_authority: str, ci_authority: str, security_authority: str,
                        source_prefix: str, ci_prefix: str, security_prefix: str,
                        current_version: str, current_source_url: str,
                        current_code_hash: str, max_age: int = 86_400,
                        proposal_ttl: int = 172_800, execution_timeout: int = 86_400,
                        caller: str | None = None) -> TargetPolicy:
        if caller != target:
            raise SentinelXError("Only the target may register its policy")
        if target in self.policies:
            raise SentinelXError("Target policy is immutable and already registered")
        if not target.startswith("0x") or len(target) != 42:
            raise SentinelXError("Target is not a valid address")
        if not owner.startswith("0x") or len(owner) != 42 or owner.lower() == "0x" + "0" * 40:
            raise SentinelXError("Owner is invalid")
        if not constitution_valid(constitution):
            raise SentinelXError("Release constitution is invalid")
        if not is_sha256(current_code_hash):
            raise SentinelXError("Current code hash must be lowercase SHA-256")
        if len({source_authority, ci_authority, security_authority}) != 3:
            raise SentinelXError("Authorities must be distinct")
        if len({source_prefix, ci_prefix, security_prefix}) != 3:
            raise SentinelXError("Prefixes must be distinct")
        if not all(raw_owner(p) for p in (source_prefix, ci_prefix, security_prefix)):
            raise SentinelXError("Prefixes must be canonical raw GitHub")
        if raw_owner(source_prefix).lower() == raw_owner(security_prefix).lower():
            raise SentinelXError("Security publisher must be independent")
        if not immutable_url(current_source_url, source_prefix):
            raise SentinelXError("Current source must be immutable")
        if not 60 <= max_age <= 90 * 24 * 60 * 60:
            raise SentinelXError("Evidence age window is invalid")
        if not 60 <= proposal_ttl <= 30 * 24 * 60 * 60:
            raise SentinelXError("Proposal TTL is invalid")
        if not 60 <= execution_timeout <= 14 * 24 * 60 * 60:
            raise SentinelXError("Execution timeout is invalid")
        fingerprint = hash_parts(
            "sentinelx-governor-v1", target, owner, project_name, constitution,
            source_authority, ci_authority, security_authority, source_prefix,
            ci_prefix, security_prefix, str(max_age), str(proposal_ttl),
            str(execution_timeout),
        )
        policy = TargetPolicy(
            owner, target, project_name, constitution, fingerprint,
            source_authority, ci_authority, security_authority, source_prefix,
            ci_prefix, security_prefix, current_version, current_source_url,
            current_code_hash, max_age, proposal_ttl, execution_timeout,
        )
        self.policies[target] = policy
        self.active[target] = 0
        self.target_proposals[target] = []
        self.history[target] = []
        return policy

    def create_proposal(self, *, target: str, candidate_version: str,
                        candidate_source_url: str, candidate_code: bytes,
                        ci_evidence_url: str, ci_evidence_id: str,
                        security_evidence_url: str, security_evidence_id: str,
                        release_intent: str, caller: str) -> ReleaseProposal:
        if target not in self.policies:
            raise SentinelXError("Target is not registered")
        policy = self.policies[target]
        if caller != policy.owner:
            raise SentinelXError("Only the registered target owner may perform this action")
        if self.active[target] != 0:
            raise SentinelXError("Target already has an active proposal")
        if candidate_version == policy.current_version:
            raise SentinelXError("Candidate version must differ from current version")
        if not candidate_code or len(candidate_code) > 768_000:
            raise SentinelXError("Candidate bytes are empty or too large")
        if not immutable_url(candidate_source_url, policy.source_prefix):
            raise SentinelXError("Candidate source is not immutable")
        if not immutable_url(ci_evidence_url, policy.ci_prefix):
            raise SentinelXError("CI evidence URL is not immutable")
        if not immutable_url(security_evidence_url, policy.security_prefix):
            raise SentinelXError("Security evidence URL is not immutable")
        if ci_evidence_id == security_evidence_id:
            raise SentinelXError("Evidence IDs must be distinct")
        for kind, evidence_id in (("ci", ci_evidence_id), ("security", security_evidence_id)):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,159}", evidence_id):
                raise SentinelXError("Evidence identifier is malformed")
            if evidence_id in self.used_evidence_ids:
                raise SentinelXError("Evidence identifier has already been used")
        candidate_hash = sha256_hex(candidate_code)
        if (target, candidate_hash) in self.installed:
            raise SentinelXError("Candidate hash has already been installed")
        if candidate_hash == policy.current_code_hash:
            raise SentinelXError("Candidate code equals current code")
        self.used_evidence_ids.update({ci_evidence_id, security_evidence_id})
        proposal = ReleaseProposal(
            self.next_id, target, policy.owner, policy.current_version,
            policy.current_source_url, policy.current_code_hash, candidate_version,
            candidate_source_url, candidate_code, candidate_hash, ci_evidence_url,
            ci_evidence_id, security_evidence_url, security_evidence_id, "",
            policy.policy_fingerprint, release_intent, self.now,
            self.now + policy.proposal_ttl_seconds,
        )
        proposal.evidence_set_hash = hash_parts(
            "sentinelx-governor-v1", proposal.parent_source_url,
            proposal.candidate_source_url, proposal.ci_evidence_url,
            proposal.ci_evidence_id, proposal.security_evidence_url,
            proposal.security_evidence_id, proposal.policy_fingerprint,
        )
        self.proposals[proposal.proposal_id] = proposal
        self.target_proposals[target].append(proposal.proposal_id)
        self.active[target] = proposal.proposal_id
        self.next_id += 1
        return proposal

    def _evidence_error(self, value: Any, kind: str, evidence_id: str,
                        issuer: str, proposal: ReleaseProposal, now: int,
                        max_age: int) -> str:
        if not isinstance(value, dict):
            return "EVIDENCE_NOT_OBJECT"
        required = ("schema", "kind", "evidence_id", "issuer", "target",
                    "parent_sha256", "candidate_sha256", "policy_fingerprint",
                    "published_at", "expires_at")
        if any(k not in value for k in required):
            return "EVIDENCE_MISSING_FIELD"
        for key in required[:8]:
            if not isinstance(value[key], str):
                return "EVIDENCE_FIELD_TYPE"
        if value["schema"] != "sentinelx-evidence-v1" or value["kind"] != kind:
            return "EVIDENCE_SCHEMA_OR_KIND"
        if value["evidence_id"] != evidence_id or value["issuer"] != issuer:
            return "EVIDENCE_ID_OR_ISSUER"
        if value["target"].lower() != proposal.target.lower():
            return "EVIDENCE_TARGET_BINDING"
        if value["parent_sha256"] != proposal.parent_code_hash:
            return "EVIDENCE_PARENT_BINDING"
        if value["candidate_sha256"] != proposal.candidate_code_hash:
            return "EVIDENCE_CANDIDATE_BINDING"
        if value["policy_fingerprint"] != proposal.policy_fingerprint:
            return "EVIDENCE_POLICY_BINDING"
        published, expires = value["published_at"], value["expires_at"]
        if isinstance(published, bool) or isinstance(expires, bool) or not isinstance(published, int) or not isinstance(expires, int):
            return "EVIDENCE_TIMESTAMP_INVALID"
        if published > now:
            return "EVIDENCE_FROM_FUTURE"
        if now - published > max_age:
            return "EVIDENCE_STALE"
        if expires < now:
            return "EVIDENCE_EXPIRED"
        if expires < published:
            return "EVIDENCE_EXPIRY_INVALID"
        return ""

    def _fetch(self, web: dict[str, Any], url: str) -> bytes:
        value = web[url]
        if isinstance(value, tuple):
            status, body = value
            if status >= 500:
                raise Retry("HTTP_5XX")
            if status >= 400:
                raise Repair("HTTP_4XX")
            if body is None:
                raise Retry("BODY_MISSING")
            return body if isinstance(body, bytes) else str(body).encode()
        return value if isinstance(value, bytes) else str(value).encode()

    def review(self, proposal_id: int, *, web: dict[str, Any], semantic: dict[str, bool] | None,
               caller: str) -> str:
        proposal = self.proposals[proposal_id]
        policy = self.policies[proposal.target]
        if caller != policy.owner:
            raise SentinelXError("Only the registered target owner may perform this action")
        if proposal.status not in (STATUS_PROPOSED, STATUS_RETRY):
            raise SentinelXError("Proposal is not reviewable")
        if self.now > proposal.expires_at:
            raise SentinelXError("Proposal has expired")
        try:
            parent = self._fetch(web, proposal.parent_source_url)
            if sha256_hex(parent) != proposal.parent_code_hash:
                raise Repair("PARENT_SOURCE_HASH_MISMATCH")
            candidate = self._fetch(web, proposal.candidate_source_url)
            if sha256_hex(candidate) != proposal.candidate_code_hash:
                raise Repair("CANDIDATE_SOURCE_HASH_MISMATCH")
            if candidate != proposal.candidate_code:
                raise Repair("CANDIDATE_BYTES_MISMATCH")
            ci_raw = self._fetch(web, proposal.ci_evidence_url)
            security_raw = self._fetch(web, proposal.security_evidence_url)
            try:
                ci = json.loads(ci_raw)
                security = json.loads(security_raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise Repair("EVIDENCE_JSON_INVALID")
            error = self._evidence_error(ci, "ci", proposal.ci_evidence_id,
                                         policy.ci_authority, proposal, self.now,
                                         policy.max_evidence_age_seconds)
            if error:
                raise Repair(error)
            error = self._evidence_error(security, "security", proposal.security_evidence_id,
                                         policy.security_authority, proposal, self.now,
                                         policy.max_evidence_age_seconds)
            if error:
                raise Repair(error)
            required_ci = ("genvm_lint", "typecheck", "schema", "direct_tests",
                           "adversarial_tests", "source_parity", "transaction_safety")
            if not isinstance(ci.get("checks"), dict) or any(ci["checks"].get(k) is not True for k in required_ci):
                raise Repair("CI_CHECK_FAILED")
            if security.get("verdict") != "PASS" or security.get("independent_review") is not True:
                raise Repair("SECURITY_NOT_PASSING")
        except Retry as exc:
            proposal.status = STATUS_RETRY
            proposal.last_review_code = str(exc)
            return proposal.status
        except Repair as exc:
            proposal.status = STATUS_REPAIR
            proposal.last_review_code = str(exc)
            return proposal.status
        if semantic is None or set(semantic) != set(SEMANTIC_VECTOR) or any(type(semantic[k]) is not bool for k in SEMANTIC_VECTOR):
            proposal.status = STATUS_RETRY
            proposal.last_review_code = "LLM_VECTOR_INVALID"
            return proposal.status
        proposal.reviewed_at = self.now
        proposal.last_review_code = ""
        if not all(semantic[k] for k in SEMANTIC_VECTOR):
            proposal.status = STATUS_REJECTED
            self.active[proposal.target] = 0
            return proposal.status
        proposal.status = STATUS_QUEUED
        proposal.execution_deadline = self.now + policy.execution_timeout_seconds
        return proposal.status

    def repair_evidence(self, proposal_id: int, *, candidate_source_url: str,
                        ci_evidence_url: str, ci_evidence_id: str,
                        security_evidence_url: str, security_evidence_id: str,
                        caller: str) -> None:
        proposal = self.proposals[proposal_id]
        policy = self.policies[proposal.target]
        if caller != policy.owner or proposal.status not in (STATUS_REPAIR, STATUS_RETRY):
            raise SentinelXError("Proposal is not awaiting evidence repair")
        if self.now > proposal.expires_at:
            raise SentinelXError("Proposal has expired")
        if not immutable_url(candidate_source_url, policy.source_prefix) or not immutable_url(ci_evidence_url, policy.ci_prefix) or not immutable_url(security_evidence_url, policy.security_prefix):
            raise SentinelXError("Replacement evidence URL is not immutable")
        if ci_evidence_id == security_evidence_id:
            raise SentinelXError("Evidence IDs must be distinct")
        for kind, evidence_id in (("ci", ci_evidence_id), ("security", security_evidence_id)):
            if evidence_id in self.used_evidence_ids:
                raise SentinelXError("Evidence identifier has already been used")
        self.used_evidence_ids.update({ci_evidence_id, security_evidence_id})
        proposal.candidate_source_url = candidate_source_url
        proposal.ci_evidence_url = ci_evidence_url
        proposal.ci_evidence_id = ci_evidence_id
        proposal.security_evidence_url = security_evidence_url
        proposal.security_evidence_id = security_evidence_id
        proposal.evidence_set_hash = hash_parts(
            "sentinelx-governor-v1", proposal.parent_source_url,
            candidate_source_url, ci_evidence_url, ci_evidence_id,
            security_evidence_url, security_evidence_id, proposal.policy_fingerprint,
        )
        proposal.status = STATUS_PROPOSED
        proposal.last_review_code = "EVIDENCE_REPAIRED"

    def retry_review(self, proposal_id: int, **kwargs: Any) -> str:
        proposal = self.proposals[proposal_id]
        if proposal.status != STATUS_RETRY:
            raise SentinelXError("Proposal is not awaiting review retry")
        return self.review(proposal_id, **kwargs)

    def cancel(self, proposal_id: int, *, caller: str) -> None:
        proposal = self.proposals[proposal_id]
        if caller != self.policies[proposal.target].owner:
            raise SentinelXError("Only owner")
        if proposal.status not in (STATUS_PROPOSED, STATUS_REPAIR, STATUS_RETRY, STATUS_QUEUED):
            raise SentinelXError("Proposal is not cancellable")
        proposal.status = STATUS_CANCELLED
        self.active[proposal.target] = 0

    def expire(self, proposal_id: int) -> None:
        proposal = self.proposals[proposal_id]
        if proposal.status not in (STATUS_PROPOSED, STATUS_REPAIR, STATUS_RETRY, STATUS_QUEUED):
            raise SentinelXError("Proposal is not expirable")
        deadline = proposal.execution_deadline if proposal.status == STATUS_QUEUED else proposal.expires_at
        if self.now <= deadline:
            raise SentinelXError("Proposal has not expired")
        proposal.status = STATUS_EXPIRED
        self.active[proposal.target] = 0

    def authorized(self, proposal_id: int, *, target: str, candidate_hash: str) -> bool:
        proposal = self.proposals[proposal_id]
        return (
            proposal.status == STATUS_QUEUED
            and proposal.target == target
            and proposal.candidate_code_hash == candidate_hash
            and self.now <= proposal.execution_deadline
            and self.active[target] == proposal_id
        )

    def confirm_install(self, proposal_id: int, *, sender: str, candidate_hash: str,
                        installed_proposal_id: int, installed_hash: str) -> None:
        proposal = self.proposals[proposal_id]
        if sender != proposal.target:
            raise SentinelXError("Only target may confirm installation")
        if proposal.status == STATUS_VERIFIED:
            if candidate_hash != proposal.candidate_code_hash:
                raise SentinelXError("Conflicting duplicate installation")
            return
        if proposal.status != STATUS_QUEUED or candidate_hash != proposal.candidate_code_hash:
            raise SentinelXError("Install confirmation does not match authorization")
        if installed_proposal_id != proposal_id or installed_hash != proposal.candidate_code_hash:
            raise SentinelXError("Finalized target attestation is invalid")
        policy = self.policies[proposal.target]
        if policy.current_code_hash != proposal.parent_code_hash:
            raise SentinelXError("Parent changed before installation")
        self.policies[proposal.target] = TargetPolicy(
            **{**policy.__dict__, "current_version": proposal.candidate_version,
               "current_source_url": proposal.candidate_source_url,
               "current_code_hash": proposal.candidate_code_hash}
        )
        proposal.status = STATUS_VERIFIED
        self.installed.add((proposal.target, proposal.candidate_code_hash))
        self.history[proposal.target].append(proposal_id)
        self.active[proposal.target] = 0

    def reconcile(self, proposal_id: int, *, caller: str, installed_proposal_id: int,
                  installed_hash: str) -> None:
        proposal = self.proposals[proposal_id]
        if caller != self.policies[proposal.target].owner:
            raise SentinelXError("Only owner")
        self.confirm_install(proposal_id, sender=proposal.target,
                             candidate_hash=proposal.candidate_code_hash,
                             installed_proposal_id=installed_proposal_id,
                             installed_hash=installed_hash)

    def timeout(self, proposal_id: int, *, installed_proposal_id: int,
                installed_hash: str) -> str:
        proposal = self.proposals[proposal_id]
        if proposal.status != STATUS_QUEUED or self.now <= proposal.execution_deadline:
            raise SentinelXError("Execution timeout is not available")
        if installed_proposal_id == proposal_id and installed_hash == proposal.candidate_code_hash:
            self.confirm_install(proposal_id, sender=proposal.target,
                                 candidate_hash=proposal.candidate_code_hash,
                                 installed_proposal_id=installed_proposal_id,
                                 installed_hash=installed_hash)
            return STATUS_VERIFIED
        if installed_proposal_id == 0 and installed_hash == self.policies[proposal.target].current_code_hash:
            proposal.status = STATUS_EXECUTION_FAILED
            self.active[proposal.target] = 0
            return proposal.status
        raise SentinelXError("Installation attestation is inconsistent")


class Repair(Exception):
    pass


class Retry(Exception):
    pass
