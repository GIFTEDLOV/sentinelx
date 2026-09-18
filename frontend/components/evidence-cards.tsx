import type { EvidenceEnvelope, EvidenceSnapshot, ReleaseProposal, TargetPolicy } from "@/lib/genlayer/types";
import { formatTimestamp, shortHash } from "@/lib/workflow";
import { CopyButton } from "./copy-button";
import { KeyValue, StatusBadge } from "./ui";

function SnapshotCard({ title, status, url, hash, evidenceId, digest, present = true, note }: { title: string; status: string; url?: string; hash?: string; evidenceId?: string; digest?: string; present?: boolean; note?: string }) {
  return <div className="evidence-card"><div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}><h3>{title}</h3><StatusBadge value={status} tone={present ? "pass" : "neutral"} /></div><div className="kv-grid" style={{ gridTemplateColumns: "1fr" }}>
    <KeyValue label="Snapshot status">{present ? "AUTHENTICATED / BOUNDED" : "NOT SUPPLIED"}</KeyValue><KeyValue label="Transport / provenance" mono><span className="copy-line"><span title={url}>{url ? shortHash(url, 16) : "—"}</span>{url && <CopyButton value={url} />}</span></KeyValue>
    {evidenceId && <KeyValue label="Evidence ID" mono>{evidenceId}</KeyValue>}{hash && <KeyValue label="Authenticated SHA-256" mono>{shortHash(hash)}</KeyValue>}{digest && <KeyValue label="Snapshot digest" mono>{shortHash(digest)}</KeyValue>}
    {note && <KeyValue label="Meaning">{note}</KeyValue>}
  </div></div>;
}

function EnvelopeCard({ title, evidence, url, evidenceId, authority }: { title: string; evidence?: EvidenceEnvelope; url?: string; evidenceId?: string; authority?: string }) {
  return <div className="evidence-card"><div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}><h3>{title}</h3><StatusBadge value={evidence ? "AUTHENTICATED" : "NOT CAPTURED"} tone={evidence ? "pass" : "neutral"} /></div><div className="kv-grid" style={{ gridTemplateColumns: "1fr" }}>
    <KeyValue label="Issuer">{evidence?.issuer || authority || "—"}</KeyValue><KeyValue label="Immutable URL" mono>{url ? shortHash(url, 16) : "—"}</KeyValue><KeyValue label="Evidence ID" mono>{evidence?.evidence_id || evidenceId || "—"}</KeyValue>
    {evidence && <><KeyValue label="Target binding" mono>{shortHash(evidence.target)}</KeyValue><KeyValue label="Parent SHA-256" mono>{shortHash(evidence.parent_sha256)}</KeyValue><KeyValue label="Candidate SHA-256" mono>{shortHash(evidence.candidate_sha256)}</KeyValue><KeyValue label="Policy binding" mono>{shortHash(evidence.policy_fingerprint)}</KeyValue><KeyValue label="Published / expires">{`${formatTimestamp(evidence.published_at)} / ${formatTimestamp(evidence.expires_at)}`}</KeyValue></>}
  </div></div>;
}

export function EvidenceCards({ proposal, policy, envelopes, snapshot, reviewWebFetchCount, reviewWebFetchUnavailable = false }: { proposal: ReleaseProposal; policy?: TargetPolicy; envelopes?: Partial<Record<"source" | "ci" | "security", EvidenceEnvelope>>; snapshot?: EvidenceSnapshot; reviewWebFetchCount?: number; reviewWebFetchUnavailable?: boolean }) {
  const required = policy?.security_attestation_mode === "REQUIRED_INDEPENDENT";
  const captured = snapshot?.status === "EVIDENCE_READY";
  const securityPresent = snapshot?.security_present ?? Boolean(envelopes?.security || proposal.security_evidence_id);
  return <div className="page-grid"><div className="notice info"><strong>Semantic review executes from authenticated stored evidence.</strong><div>Review-time web fetches: {reviewWebFetchUnavailable ? "UNAVAILABLE" : typeof reviewWebFetchCount === "number" ? reviewWebFetchCount : captured ? 0 : "not proven until capture"}.</div></div><div className="evidence-grid">
    {captured ? <SnapshotCard title="SOURCE SNAPSHOT" status="PINNED" url={snapshot?.parent_source_url} hash={snapshot?.parent_source_hash} digest={snapshot?.snapshot_digest} note="Parent bytes and the frozen candidate bytes are authenticated before review." /> : <EnvelopeCard title="SOURCE SNAPSHOT" url={proposal.parent_source_url} authority={policy?.source_authority} />}
    {captured ? <SnapshotCard title="CI SNAPSHOT" status="PINNED" url={snapshot?.ci_evidence_url} hash={snapshot?.ci_evidence_hash} evidenceId={snapshot?.ci_evidence_id} digest={snapshot?.snapshot_digest} /> : <EnvelopeCard title="CI SNAPSHOT" evidence={envelopes?.ci} url={proposal.ci_evidence_url} evidenceId={proposal.ci_evidence_id} authority={policy?.ci_authority} />}
    {captured && securityPresent ? <SnapshotCard title={`EXTERNAL SECURITY SNAPSHOT — ${required ? "required" : "optional"}`} status="PINNED" url={snapshot?.security_evidence_url} hash={snapshot?.security_evidence_hash} evidenceId={snapshot?.security_evidence_id} digest={snapshot?.snapshot_digest} note={required ? "Independent artifact is a readiness prerequisite; validators still review source and CI." : "Supporting evidence only; it does not replace validator judgment."} /> : <SnapshotCard title={`EXTERNAL SECURITY SNAPSHOT — ${required ? "required" : "optional"}`} status={required ? "REQUIRED" : "OPTIONAL"} present={false} note={required ? "Evidence capture is blocked until a valid independent artifact is supplied." : "No external security audit supplied. This is not an audit or independent-review claim."} />}
  </div></div>;
}
