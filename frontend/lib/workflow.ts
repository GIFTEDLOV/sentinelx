import { SEMANTIC_FIELDS, type EvidenceEnvelope, type SemanticVector, type TransactionLifecycle } from "./genlayer/types";

export { SEMANTIC_FIELDS };

export interface CandidateSourceCheck {
  valid: boolean;
  commit?: string;
  owner?: string;
  repository?: string;
  reason?: string;
}

/** Strictly accepts raw GitHub content addressed by a 40-character commit. */
export function validateImmutableGitHubUrl(value: string, requiredPrefix?: string): CandidateSourceCheck {
  if (!value || value.length > 512 || /[^\x00-\x7F]/.test(value)) return { valid: false, reason: "URL must be ASCII and bounded" };
  if (/[\\%?#]|\.\.?\//.test(value) || value.includes("//", 8)) {
    return { valid: false, reason: "path separators, aliases and encoded query/path data are not allowed" };
  }
  const match = /^https:\/\/raw\.githubusercontent\.com\/([A-Za-z0-9][A-Za-z0-9_.-]*)\/([A-Za-z0-9][A-Za-z0-9_.-]*)\/([0-9a-f]{40})\/([A-Za-z0-9][A-Za-z0-9._/-]*)$/.exec(value);
  if (!match) return { valid: false, reason: "use an immutable raw.githubusercontent.com commit URL" };
  const path = match[4];
  const segments = path.split("/");
  if (segments.some((segment) => segment === "." || segment === ".." || segment.length === 0)) {
    return { valid: false, reason: "ambiguous path segment" };
  }
  if (requiredPrefix && value.slice(0, requiredPrefix.length) !== requiredPrefix) {
    return { valid: false, reason: "URL does not match the registered source prefix" };
  }
  return { valid: true, owner: match[1], repository: match[2], commit: match[3] };
}

export async function sha256Hex(bytes: ArrayBuffer | Uint8Array): Promise<string> {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const digest = await crypto.subtle.digest("SHA-256", view as BufferSource);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function deriveApproval(vector: SemanticVector): boolean {
  return SEMANTIC_FIELDS.every((field) => vector[field] === true);
}

export const PROPOSAL_STATUS_LABELS: Record<string, string> = {
  PROPOSED: "PROPOSED · UNASSESSED",
  EVIDENCE_STAGED: "EVIDENCE STAGED",
  EVIDENCE_READY: "EVIDENCE AUTHENTICATED",
  EVIDENCE_REPAIR_REQUIRED: "EVIDENCE REPAIR REQUIRED",
  EVIDENCE_RETRY_REQUIRED: "EVIDENCE RETRY REQUIRED",
  REVIEW_RETRY_REQUIRED: "SEMANTIC REVIEW RETRY REQUIRED",
  REJECTED: "REJECTED",
  UPGRADE_QUEUED: "APPROVED · AWAITING INSTALL",
  VERIFIED: "VERIFIED · INSTALLED",
  EXPIRED: "EXPIRED",
  CANCELLED: "CANCELLED",
  EXECUTION_FAILED: "INSTALLATION FAILED",
};

export function proposalStatusLabel(status: string): string {
  return PROPOSAL_STATUS_LABELS[status] || status.replaceAll("_", " ");
}

export function isSuccessfulFinalized(lifecycle: TransactionLifecycle, executionResult?: string): boolean {
  return lifecycle.state === "finalized" && executionResult === "FINISHED_WITH_RETURN";
}

export function pollingRecoveryAction(): { action: "resume-tracking"; rebroadcast: false } {
  return { action: "resume-tracking", rebroadcast: false };
}

export function proposalPreconditions(input: {
  configured: boolean;
  policyActive: boolean;
  activeProposal: number;
  candidateAlreadyInstalled: boolean;
  candidateHash?: string;
}): { ok: boolean; reasons: string[] } {
  const reasons: string[] = [];
  if (!input.configured) reasons.push("SentinelX governor and target addresses are not configured");
  if (!input.policyActive) reasons.push("target policy is not active");
  if (input.activeProposal > 0) reasons.push("target already has an active proposal");
  if (input.candidateAlreadyInstalled) reasons.push("candidate is already installed");
  if (!input.candidateHash) reasons.push("candidate bytes have not been frozen and hashed");
  return { ok: reasons.length === 0, reasons };
}

export function mapEvidenceDisplay(evidence: EvidenceEnvelope | undefined, kind: string) {
  if (!evidence) return { kind, present: false, status: "MISSING" as const };
  return {
    kind,
    present: true,
    status: "UNVERIFIED" as const,
    issuer: evidence.issuer,
    url: evidence.url || evidence.evidence_id,
    evidenceId: evidence.evidence_id,
    target: evidence.target,
    parent: evidence.parent_sha256,
    candidate: evidence.candidate_sha256,
    policy: evidence.policy_fingerprint,
    publishedAt: evidence.published_at,
    expiresAt: evidence.expires_at,
    verdict: evidence.verdict,
    independentReview: evidence.independent_review,
  };
}

export function isProductionFixtureAllowed(): boolean {
  return false;
}

export function shortAddress(value?: string, length = 6): string {
  if (!value) return "—";
  if (value.length <= length * 2 + 3) return value;
  return `${value.slice(0, length + 2)}…${value.slice(-length)}`;
}

export function shortHash(value?: string, length = 10): string {
  if (!value) return "—";
  if (value.length <= length * 2 + 3) return value;
  return `${value.slice(0, length)}…${value.slice(-length)}`;
}

export function formatTimestamp(value?: number): string {
  if (!value) return "—";
  return new Date(value < 10_000_000_000 ? value * 1000 : value).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatRelative(value?: number): string {
  if (!value) return "—";
  const then = value < 10_000_000_000 ? value * 1000 : value;
  const minutes = Math.round((Date.now() - then) / 60000);
  if (Math.abs(minutes) < 1) return "just now";
  if (minutes < 60) return `${Math.abs(minutes)}m ${minutes > 0 ? "ago" : "from now"}`;
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return `${Math.abs(hours)}h ${hours > 0 ? "ago" : "from now"}`;
  return `${Math.abs(Math.round(hours / 24))}d ${hours > 0 ? "ago" : "from now"}`;
}
