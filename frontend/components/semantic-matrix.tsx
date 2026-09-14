import { SEMANTIC_FIELDS, type SemanticVector } from "@/lib/genlayer/types";
import { StatusBadge } from "./ui";

const LABELS: Record<(typeof SEMANTIC_FIELDS)[number], string> = {
  storage_layout_compatible: "Storage layout compatible",
  public_interface_compatible: "Public interface compatible",
  user_rights_preserved: "User rights preserved",
  no_privilege_escalation: "No privilege escalation",
  upgrade_authority_preserved: "Upgrade authority preserved",
  consensus_integrity_preserved: "Consensus integrity preserved",
  finality_safety_preserved: "Finality safety preserved",
  evidence_trust_preserved: "Evidence trust preserved",
  fund_flow_safe: "Fund flow safe",
  external_fetch_surface_safe: "External fetch surface safe",
  liveness_preserved: "Liveness preserved",
  behavioral_scope_matches_release: "Behavioral scope matches release",
  migration_safety_preserved: "Migration safety preserved",
  constitution_satisfied: "Release Constitution satisfied",
};

export function SemanticMatrix({ vector }: { vector?: SemanticVector }) {
  return <div className="matrix" aria-label="14-field semantic safety vector">{SEMANTIC_FIELDS.map((field) => { const value = vector?.[field]; const state = value === true ? "PASS" : value === false ? "FAIL" : "NOT REVIEWED"; return <div className="matrix-row" key={field}><span className="matrix-name">{LABELS[field]} <span className="dim">{field}</span></span><span className="matrix-state"><StatusBadge value={state} tone={state === "PASS" ? "pass" : state === "FAIL" ? "failed" : "not-reviewed"} /></span></div>; })}</div>;
}

export { LABELS as SEMANTIC_LABELS };
