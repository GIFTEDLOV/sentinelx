"use client";

import { Activity as ActivityIcon, ArrowRight, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { listTransactions } from "@/lib/genlayer/transactions";
import type { TransactionRecord } from "@/lib/genlayer/types";
import { shortHash } from "@/lib/workflow";
import { Card, EmptyState, PageHeader, StatusBadge } from "./ui";

export function ActivityPage() {
  const [records, setRecords] = useState<TransactionRecord[]>([]); const [filter, setFilter] = useState("");
  useEffect(() => { const refresh = () => setRecords(listTransactions()); refresh(); window.addEventListener("sentinelx:transactions", refresh); return () => window.removeEventListener("sentinelx:transactions", refresh); }, []);
  const visible = records.filter((record) => `${record.operation} ${record.hash} ${record.verification}`.toLowerCase().includes(filter.toLowerCase()));
  return <div className="page"><PageHeader eyebrow="Workspace / Activity" title="Transaction activity" description="A durable local record of returned hashes and lifecycle observations. Ambiguous polling is resumable and never silently resubmitted." /><Card title="Transaction center" action={<div style={{ position: "relative" }}><Search size={14} className="dim" style={{ position: "absolute", left: 10, top: 12 }} /><input className="search-input" style={{ paddingLeft: 31, width: 220 }} placeholder="Filter activity" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter activity" /></div>}>{visible.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>Operation</th><th>Hash</th><th>Lifecycle</th><th>Execution</th><th>Verification</th><th /></tr></thead><tbody>{visible.map((record) => <tr key={`${record.operation}-${record.hash}`}><td>{record.operation}</td><td className="mono" title={record.hash}>{shortHash(record.hash, 14)}</td><td>{record.lifecycle.storedStatus || record.lifecycle.state}</td><td>{record.executionResult || "—"}</td><td><StatusBadge value={record.verification} /></td><td>{record.proposalId ? <Link className="button ghost" href={`/app/releases/${record.proposalId}`}>Release <ArrowRight size={12} /></Link> : null}</td></tr>)}</tbody></table></div> : <EmptyState icon={<ActivityIcon size={19} />} title="No transaction activity" description="Returned hashes will appear here after a guarded write. No chain writes are performed by this Phase 2B build." />}</Card></div>;
}
