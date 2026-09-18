import { beforeEach, describe, expect, it } from "vitest";
import { getSentinelXConfig } from "./genlayer/chains";
import { clearTransactions, listTransactions, saveTransaction } from "./genlayer/transactions";
import { SEMANTIC_FIELDS, type SemanticVector } from "./genlayer/types";
import { deriveApproval, isProductionFixtureAllowed, isSuccessfulFinalized, mapEvidenceDisplay, pollingRecoveryAction, proposalPreconditions, proposalStatusLabel, sha256Hex, validateImmutableGitHubUrl } from "./workflow";

const TRUE_VECTOR = Object.fromEntries(SEMANTIC_FIELDS.map((field) => [field, true])) as SemanticVector;
const COMMIT = "7e3b552c8b0471db0411206fdbc743dd12ef4e80";
const RAW = `https://raw.githubusercontent.com/GIFTEDLOV/sentinelx/${COMMIT}/contracts/protected_app_v2_safe.py`;

describe("SentinelX frontend safety workflow", () => {
  beforeEach(() => { clearTransactions(); });

  it("validates an unconfigured console without inventing addresses", () => {
    const original = { governor: process.env.NEXT_PUBLIC_SENTINELX_GOVERNOR_ADDRESS, target: process.env.NEXT_PUBLIC_SENTINELX_CANONICAL_TARGET_ADDRESS };
    delete process.env.NEXT_PUBLIC_SENTINELX_GOVERNOR_ADDRESS; delete process.env.NEXT_PUBLIC_SENTINELX_CANONICAL_TARGET_ADDRESS;
    expect(getSentinelXConfig().status).toBe("unconfigured");
    if (original.governor) process.env.NEXT_PUBLIC_SENTINELX_GOVERNOR_ADDRESS = original.governor;
    if (original.target) process.env.NEXT_PUBLIC_SENTINELX_CANONICAL_TARGET_ADDRESS = original.target;
  });
  it("fails closed for non-canonical production addresses", () => {
    const environment = process.env as Record<string, string | undefined>;
    const originalNodeEnv = environment.NODE_ENV;
    const originalGovernor = process.env.NEXT_PUBLIC_SENTINELX_GOVERNOR_ADDRESS;
    const originalTarget = process.env.NEXT_PUBLIC_SENTINELX_CANONICAL_TARGET_ADDRESS;
    environment.NODE_ENV = "production";
    process.env.NEXT_PUBLIC_SENTINELX_GOVERNOR_ADDRESS = "0x1111111111111111111111111111111111111111";
    process.env.NEXT_PUBLIC_SENTINELX_CANONICAL_TARGET_ADDRESS = "0x2222222222222222222222222222222222222222";
    expect(getSentinelXConfig().status).toBe("unconfigured");
    if (originalNodeEnv === undefined) delete environment.NODE_ENV; else environment.NODE_ENV = originalNodeEnv;
    if (originalGovernor === undefined) delete process.env.NEXT_PUBLIC_SENTINELX_GOVERNOR_ADDRESS; else process.env.NEXT_PUBLIC_SENTINELX_GOVERNOR_ADDRESS = originalGovernor;
    if (originalTarget === undefined) delete process.env.NEXT_PUBLIC_SENTINELX_CANONICAL_TARGET_ADDRESS; else process.env.NEXT_PUBLIC_SENTINELX_CANONICAL_TARGET_ADDRESS = originalTarget;
  });

  it("accepts only immutable raw GitHub commit URLs", () => { expect(validateImmutableGitHubUrl(RAW).valid).toBe(true); });
  it("rejects mutable branches", () => { expect(validateImmutableGitHubUrl("https://raw.githubusercontent.com/GIFTEDLOV/sentinelx/main/contracts/protected_app_v2_safe.py").valid).toBe(false); });
  it("rejects traversal, encoding and separator aliases", () => { expect(validateImmutableGitHubUrl(`https://raw.githubusercontent.com/GIFTEDLOV/sentinelx/${COMMIT}/contracts/../protected_app_v2_safe.py`).valid).toBe(false); expect(validateImmutableGitHubUrl(`https://raw.githubusercontent.com/GIFTEDLOV/sentinelx/${COMMIT}/contracts/%2e%2e/app.py`).valid).toBe(false); expect(validateImmutableGitHubUrl(`https://raw.githubusercontent.com/GIFTEDLOV/sentinelx/${COMMIT}/contracts\\app.py`).valid).toBe(false); });
  it("hashes candidate bytes deterministically", async () => { expect(await sha256Hex(new TextEncoder().encode("SentinelX"))).toBe("447694d453302254042d78de4f5820e83027644b185051b99df89b957d41a4b8"); });
  it("blocks proposal collisions and missing candidate freezes", () => { const result = proposalPreconditions({ configured: true, policyActive: true, activeProposal: 9, candidateAlreadyInstalled: false }); expect(result.ok).toBe(false); expect(result.reasons).toContain("target already has an active proposal"); });
  it("requires all fourteen semantic booleans", () => { expect(deriveApproval(TRUE_VECTOR)).toBe(true); const changed = { ...TRUE_VECTOR, fund_flow_safe: false }; expect(deriveApproval(changed)).toBe(false); });
  it("does not approve unresolved semantic fields", () => { const unresolved = { ...TRUE_VECTOR, constitution_satisfied: null }; expect(deriveApproval(unresolved)).toBe(false); });
  it("keeps Accepted distinct from Finalized", () => { expect(isSuccessfulFinalized({ state: "decided", storedStatus: "Accepted" }, "FINISHED_WITH_RETURN")).toBe(false); expect(isSuccessfulFinalized({ state: "finalized", storedStatus: "Finalized" }, "FINISHED_WITH_RETURN")).toBe(true); });
  it("keeps finalized execution failure unsuccessful", () => { expect(isSuccessfulFinalized({ state: "finalized", storedStatus: "Finalized" }, "FINISHED_WITH_ERROR")).toBe(false); });
  it("persists returned transaction records for the center", () => { saveTransaction({ operation: "review", hash: `0x${"a".repeat(64)}`, submittedAt: new Date().toISOString(), lifecycle: { state: "processing" }, childTransactionIds: [], verification: "pending" }); expect(listTransactions()).toHaveLength(1); expect(listTransactions()[0].hash).toContain("aaaa"); });
  it("recovers ambiguous polling by resuming the same hash", () => { expect(pollingRecoveryAction()).toEqual({ action: "resume-tracking", rebroadcast: false }); });
  it("maps evidence bindings without turning them into approval", () => { const mapped = mapEvidenceDisplay({ schema: "sentinelx-evidence-v1", kind: "security", evidence_id: "security-1", url: "https://immutable/security-1.json", issuer: "independent", target: "target", parent_sha256: "parent", candidate_sha256: "candidate", policy_fingerprint: "policy", published_at: 1, expires_at: 2 }, "SECURITY"); expect(mapped.url).toContain("immutable/security"); expect(mapped.status).toBe("UNVERIFIED"); });
  it("prohibits preview fixtures in production", () => { expect(isProductionFixtureAllowed()).toBe(false); });
  it("keeps every governor lifecycle state visually distinct", () => {
    expect(proposalStatusLabel("PROPOSED")).toContain("UNASSESSED");
    expect(proposalStatusLabel("EVIDENCE_STAGED")).toBe("EVIDENCE STAGED");
    expect(proposalStatusLabel("EVIDENCE_READY")).toContain("AUTHENTICATED");
    expect(proposalStatusLabel("UPGRADE_QUEUED")).toContain("AWAITING INSTALL");
    expect(proposalStatusLabel("VERIFIED")).toContain("INSTALLED");
    expect(proposalStatusLabel("REJECTED")).toBe("REJECTED");
  });
});
