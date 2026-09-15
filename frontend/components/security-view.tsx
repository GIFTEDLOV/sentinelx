import type { TargetPolicy } from "@/lib/genlayer/types";
import { Card, KeyValue, Notice, StatusBadge } from "./ui";

export function SecurityView({ policy }: { policy: TargetPolicy }) {
  const required = policy.security_attestation_mode === "REQUIRED_INDEPENDENT";
  return <div className="page-grid grid-2">
    <Card title="Security posture" subtitle="Live posture is derived from the registered V2 policy and finalized release history."><div className="kv-grid">
      <KeyValue label="Attestation mode">{policy.security_attestation_mode}</KeyValue><KeyValue label="Owner bypass">Blocked by target authorization</KeyValue>
      <KeyValue label="Upgrade authority">SentinelX governor only</KeyValue><KeyValue label="Evidence freshness">{policy.max_evidence_age_seconds}s maximum</KeyValue>
      <KeyValue label="Policy state"><StatusBadge value={policy.active ? "ACTIVE" : "INACTIVE"} tone={policy.active ? "verified" : "rejected"} /></KeyValue>
    </div></Card>
    <Card title="External security attestation" subtitle={required ? "The registered independent publisher is an authorization prerequisite." : "External attestation is configurable and is not required in OPTIONAL mode."}>
      <div className="kv-grid" style={{ gridTemplateColumns: "1fr" }}><KeyValue label="Source authority">{policy.source_authority}</KeyValue><KeyValue label="CI authority">{policy.ci_authority}</KeyValue><KeyValue label="Security authority">{policy.security_authority || "Not configured"}</KeyValue></div>
      {required ? <Notice title="Independent review required" tone="warning">SentinelX will not mark evidence ready until authenticated security evidence from a distinct publisher is available. Same-owner evidence is rejected.</Notice> : <Notice title="No external security audit supplied" tone="info">OPTIONAL mode does not claim an auditor or independent review when no external artifact exists. Validators independently evaluate the authenticated snapshots.</Notice>}
    </Card>
    <Card title="Protected invariants" className="span-2"><div className="matrix">
      <div className="matrix-row"><span className="matrix-name">Owner cannot directly install code</span><StatusBadge value="ENFORCED" tone="pass" /></div>
      <div className="matrix-row"><span className="matrix-name">Candidate bytes and hash are frozen</span><StatusBadge value="ENFORCED" tone="pass" /></div>
      <div className="matrix-row"><span className="matrix-name">Authorization expires before late child execution</span><StatusBadge value="ENFORCED" tone="pass" /></div>
      <div className="matrix-row"><span className="matrix-name">Evidence is authenticated before semantic review</span><StatusBadge value="ENFORCED" tone="pass" /></div>
      <div className="matrix-row"><span className="matrix-name">Semantic review-time web fetches</span><StatusBadge value="0" tone="pass" /></div>
    </div></Card>
  </div>;
}
