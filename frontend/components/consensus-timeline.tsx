import type { TransactionLifecycle } from "@/lib/genlayer/types";
import { StatusBadge } from "./ui";

const CONSENSUS = ["Submitted", "Proposing", "Committing", "Revealing", "Accepted", "Finalized"];
const INSTALLATION = ["Upgrade child", "Installation", "Confirmation", "Verified"];

function Timeline({ title, items, current, final }: { title: string; items: string[]; current?: string; final?: boolean }) {
  const currentIndex = current ? items.indexOf(current) : -1;
  return <CardTimeline title={title}><div className="timeline">{items.map((item, index) => { const done = currentIndex >= index || (final && currentIndex === -1); const active = current === item; return <div className={`timeline-item ${done ? "done" : ""} ${active ? "current" : ""}`} key={item}><span className="timeline-dot" /><span className="timeline-label">{item}</span><span className="timeline-meta">{active ? "Observed current state" : done ? "Observed" : "Not observed"}</span></div>; })}</div></CardTimeline>;
}

function CardTimeline({ title, children }: { title: string; children: React.ReactNode }) { return <section className="card card-pad"><div style={{ display: "flex", justifyContent: "space-between", marginBottom: 18 }}><h2 className="card-title">{title}</h2><StatusBadge value="Canonical data only" tone="neutral" /></div>{children}</section>; }

export function ConsensusTimeline({ lifecycle, verified = false }: { lifecycle?: TransactionLifecycle; verified?: boolean }) {
  const current = lifecycle?.storedStatus;
  const consensusCurrent = current === "Accepted" ? "Accepted" : current === "Finalized" ? "Finalized" : current === "Proposing" ? "Proposing" : current === "Committing" ? "Committing" : current === "Revealing" ? "Revealing" : current === "Pending" ? "Submitted" : undefined;
  return <div className="page-grid grid-2"><Timeline title="CONSENSUS" items={CONSENSUS} current={consensusCurrent} /><Timeline title="LIFECYCLE" items={["Submitted", "Processing", "Accepted", "Finalized"]} current={consensusCurrent === "Finalized" ? "Finalized" : consensusCurrent === "Accepted" ? "Accepted" : consensusCurrent ? "Processing" : undefined} /><Timeline title="EXECUTION" items={INSTALLATION} current={verified ? "Verified" : undefined} final={false} /></div>;
}
