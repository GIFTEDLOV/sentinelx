export const SEMANTIC_FIELDS = [
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
] as const;

export type SemanticField = (typeof SEMANTIC_FIELDS)[number];
export type SemanticVector = Record<SemanticField, boolean | null>;

export type ProposalStatus =
  | "PROPOSED"
  | "EVIDENCE_STAGED"
  | "EVIDENCE_READY"
  | "EVIDENCE_REPAIR_REQUIRED"
  | "EVIDENCE_RETRY_REQUIRED"
  | "REVIEW_RETRY_REQUIRED"
  | "REJECTED"
  | "UPGRADE_QUEUED"
  | "VERIFIED"
  | "EXPIRED"
  | "CANCELLED"
  | "EXECUTION_FAILED"
  | "UNKNOWN";

export type EvidenceKind = "source" | "ci" | "security";
export type SecurityAttestationMode = "OPTIONAL" | "REQUIRED_INDEPENDENT";

export interface TargetPolicy {
  target: string;
  owner: string;
  project_name: string;
  release_constitution: string;
  policy_fingerprint: string;
  source_authority: string;
  ci_authority: string;
  security_authority: string;
  source_prefix: string;
  ci_prefix: string;
  security_prefix: string;
  security_attestation_mode: SecurityAttestationMode;
  security_configured?: boolean;
  current_version: string;
  current_source_url: string;
  current_code_hash: string;
  max_evidence_age_seconds: number;
  proposal_ttl_seconds: number;
  execution_timeout_seconds: number;
  active: boolean;
}

export interface ReleaseProposal {
  proposal_id: number;
  target: string;
  proposer: string;
  parent_version: string;
  parent_source_url: string;
  parent_code_hash: string;
  candidate_version: string;
  candidate_source_url: string;
  candidate_code_hash: string;
  ci_evidence_url: string;
  ci_evidence_id: string;
  security_evidence_url: string;
  security_evidence_id: string;
  evidence_set_hash: string;
  policy_fingerprint: string;
  release_intent: string;
  created_at: number;
  expires_at: number;
  reviewed_at: number;
  execution_deadline: number;
  status: ProposalStatus;
  last_review_code: string;
  semantic?: SemanticVector;
}

export interface EvidenceSnapshot {
  status: string;
  schema?: string;
  proposal_id?: number;
  evidence_identity?: string;
  parent_source_url?: string;
  parent_source_hash?: string;
  candidate_source_url?: string;
  candidate_source_hash?: string;
  ci_evidence_url?: string;
  ci_evidence_id?: string;
  ci_evidence_hash?: string;
  security_evidence_url?: string;
  security_evidence_id?: string;
  security_evidence_hash?: string;
  security_present?: boolean;
  policy_fingerprint?: string;
  captured_at?: number;
  snapshot_digest?: string;
}

export interface EvidenceEnvelope {
  schema: "sentinelx-evidence-v1" | string;
  kind: EvidenceKind;
  evidence_id: string;
  issuer: string;
  target: string;
  parent_sha256: string;
  candidate_sha256: string;
  policy_fingerprint: string;
  published_at: number;
  expires_at: number;
  checks?: Record<string, boolean>;
  verdict?: string;
  independent_review?: boolean;
  url?: string;
}

export type LifecycleState =
  | "processing"
  | "decided"
  | "finalized"
  | "canceled"
  | "unknown";

export interface TransactionLifecycle {
  state: LifecycleState;
  phase?: string;
  outcome?: string;
  storedStatus?: string;
  projectedStatus?: string;
  resolutionAction?: string;
  decisionId?: string | null;
  decisionActive?: boolean;
}

export interface TransactionRecord {
  operation: string;
  hash: string;
  target?: string;
  proposalId?: number;
  submittedAt: string;
  lifecycle: TransactionLifecycle;
  executionResult?: string;
  childTransactionIds: string[];
  verification: "pending" | "finalized" | "successful" | "failed" | "ambiguous";
}

export type ConfigurationStatus = "unconfigured" | "configured" | "wrong-network" | "rpc-unavailable";

export interface SentinelXConfig {
  rpcUrl: string;
  chainId: number;
  governorAddress?: string;
  canonicalTargetAddress?: string;
  feeProfileUrl?: string;
  status: ConfigurationStatus;
}
