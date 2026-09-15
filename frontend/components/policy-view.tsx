import type { TargetPolicy } from "@/lib/genlayer/types";
import { SEMANTIC_FIELDS } from "@/lib/genlayer/types";
import { shortHash } from "@/lib/workflow";
import { CopyButton } from "./copy-button";
import { Card, KeyValue, Notice } from "./ui";
import { SEMANTIC_LABELS } from "./semantic-matrix";

export function PolicyView({ policy }: { policy: TargetPolicy }) {
  const optional = policy.security_attestation_mode === "OPTIONAL";
  return <div className="page-grid">
    <Notice title="Immutable after registration" tone="info">This SentinelX V2 policy is rendered from the registered governor record. It has no edit path after registration.</Notice>
    <div className="page-grid grid-2">
      <Card title="Registered policy" subtitle="Authority and lifecycle bounds"><div className="kv-grid">
        <KeyValue label="Project">{policy.project_name}</KeyValue><KeyValue label="Active">{String(policy.active)}</KeyValue>
        <KeyValue label="Owner" mono><span className="copy-line">{policy.owner}<CopyButton value={policy.owner} /></span></KeyValue>
        <KeyValue label="Target" mono><span className="copy-line">{policy.target}<CopyButton value={policy.target} /></span></KeyValue>
        <KeyValue label="Policy fingerprint" mono><span className="copy-line">{shortHash(policy.policy_fingerprint)}<CopyButton value={policy.policy_fingerprint} /></span></KeyValue>
        <KeyValue label="Security attestation">{policy.security_attestation_mode}</KeyValue>
        <KeyValue label="Current version">{policy.current_version}</KeyValue><KeyValue label="Current source" mono>{policy.current_source_url}</KeyValue>
        <KeyValue label="Current code hash" mono>{policy.current_code_hash}</KeyValue><KeyValue label="Evidence max age">{policy.max_evidence_age_seconds}s</KeyValue>
        <KeyValue label="Proposal TTL">{policy.proposal_ttl_seconds}s</KeyValue><KeyValue label="Execution timeout">{policy.execution_timeout_seconds}s</KeyValue>
      </div></Card>
      <Card title="Evidence authorities" subtitle="Transport prefixes and identity bindings are part of the immutable policy"><div className="kv-grid" style={{ gridTemplateColumns: "1fr" }}>
        <KeyValue label="Source authority">{policy.source_authority}</KeyValue><KeyValue label="Source prefix" mono>{policy.source_prefix}</KeyValue>
        <KeyValue label="CI authority">{policy.ci_authority}</KeyValue><KeyValue label="CI prefix" mono>{policy.ci_prefix}</KeyValue>
        <KeyValue label="Security authority">{policy.security_authority || (optional ? "Not configured" : "Missing")}</KeyValue>
        <KeyValue label="Security prefix" mono>{policy.security_prefix || (optional ? "Not configured" : "Missing")}</KeyValue>
      </div></Card>
    </div>
    {optional ? <Notice title="No external security audit supplied" tone="info">OPTIONAL mode permits a release without an external security artifact. GenLayer validators still make the substantive 14-field semantic/security decision from authenticated source and CI snapshots. This state is not an audit or independent-review claim.</Notice> : <Notice title="Independent security evidence required" tone="warning">REQUIRED_INDEPENDENT mode blocks evidence readiness until a valid, independently published and fully bound security artifact is captured.</Notice>}
    <Card title="Release Constitution" subtitle="The full registered constitution is the adjudication boundary"><div className="constitution">{policy.release_constitution}</div></Card>
    <Card title="14 authorization-driving requirements" subtitle="Every field must be true. There is no confidence threshold or majority rule."><div className="matrix">{SEMANTIC_FIELDS.map((field, index) => <div className="matrix-row" key={field}><span className="matrix-name">{String(index + 1).padStart(2, "0")} · {SEMANTIC_LABELS[field]} <span className="dim">{field}</span></span><span className="matrix-state" style={{ color: "var(--text-dim)", fontFamily: "var(--mono)", fontSize: 11 }}>required = true</span></div>)}</div></Card>
  </div>;
}
