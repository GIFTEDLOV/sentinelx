"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpDown, FolderKanban, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { getTargetIds, getTargetPolicy } from "@/lib/genlayer/reads";
import { getSentinelXConfig, previewEnabled } from "@/lib/genlayer/chains";
import { PREVIEW_ONLY_FIXTURES } from "@/lib/preview-fixtures";
import { shortAddress, shortHash, formatRelative } from "@/lib/workflow";
import type { TargetPolicy } from "@/lib/genlayer/types";
import { Card, EmptyState, ErrorState, PageHeader, PreviewRibbon, Skeleton, StatusBadge } from "./ui";

export function ProjectsDirectory() {
  const config = getSentinelXConfig(); const [filter, setFilter] = useState(""); const [sort, setSort] = useState<"name" | "version">("name");
  const preview = previewEnabled();
  const query = useQuery({ queryKey: ["target-policies", config.governorAddress], enabled: config.status === "configured", queryFn: async () => { const ids = await getTargetIds(); return Promise.all(ids.map((id) => getTargetPolicy(id))); } });
  const policies = useMemo(() => preview ? [PREVIEW_ONLY_FIXTURES.policy] : query.data || [], [preview, query.data]);
  const visible = useMemo(() => policies.filter((policy) => `${policy.project_name} ${policy.target} ${policy.current_version}`.toLowerCase().includes(filter.toLowerCase())).sort((a, b) => sort === "name" ? a.project_name.localeCompare(b.project_name) : a.current_version.localeCompare(b.current_version)), [policies, filter, sort]);
  return <div className="page"><PageHeader eyebrow="Workspace / Projects" title="Protected contracts" description="Every registered target is governed by an immutable Release Constitution." actions={<Link className="button primary" href="/app/projects/new"><Plus size={14} />Register contract</Link>} />{preview && <PreviewRibbon />}{config.status !== "configured" && !preview ? <Card><EmptyState icon={<FolderKanban size={19} />} title="Deployment not configured" description="No canonical governor and target addresses are configured. Connect the eventual Studionet deployment to populate this directory." /></Card> : query.isLoading ? <Card><div className="page-grid card-pad"><Skeleton /><Skeleton /><Skeleton /></div></Card> : query.isError ? <Card><ErrorState description="The governor could not be read. No fixture data was substituted." retry={() => void query.refetch()} /></Card> : visible.length === 0 ? <Card><EmptyState title="No matching contracts" description="Try a different project name or target address." /></Card> : <Card title={`${visible.length} protected ${visible.length === 1 ? "contract" : "contracts"}`} action={<div style={{ display: "flex", gap: 8 }}><div style={{ position: "relative" }}><Search size={14} className="dim" style={{ position: "absolute", left: 10, top: 12 }} /><input className="search-input" style={{ paddingLeft: 31, width: 220 }} value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search projects" aria-label="Search projects" /></div><button className="icon-button" onClick={() => setSort(sort === "name" ? "version" : "name")} aria-label="Sort projects"><ArrowUpDown size={14} /></button></div>}><div className="table-wrap"><table className="data-table"><thead><tr><th>Project</th><th>Target</th><th>Version</th><th>Policy</th><th>Last verified</th><th>Security posture</th></tr></thead><tbody>{visible.map((policy: TargetPolicy) => <tr key={policy.target}><td><Link href={`/app/projects/${policy.target}`}><strong>{policy.project_name}</strong></Link></td><td className="mono">{shortAddress(policy.target)}</td><td className="mono">{policy.current_version}</td><td><StatusBadge value={policy.active ? "ACTIVE" : "INACTIVE"} tone={policy.active ? "verified" : "rejected"} /></td><td className="dim">{formatRelative()}</td><td><StatusBadge value="CONSTITUTION BOUND" tone="info" /></td></tr>)}</tbody></table></div></Card>}
  </div>;
}
