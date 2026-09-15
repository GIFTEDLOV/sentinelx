"use client";

import { LockKeyhole, ShieldPlus } from "lucide-react";
import { useState } from "react";
import { getSentinelXConfig, isAddress } from "@/lib/genlayer/chains";
import { Card, KeyValue, Notice, PageHeader } from "./ui";

export function RegisterProject() {
  const config = getSentinelXConfig();
  const [target, setTarget] = useState("");
  const [project, setProject] = useState("");
  const [source, setSource] = useState("");
  return <div className="page"><PageHeader eyebrow="Workspace / Register" title="Register a protected contract" description="Registration is initiated through the target owner flow and results in a finalized governor child consequence. It is not an arbitrary governor shortcut." /><Card title="Registration preflight" subtitle="V2 exposes OPTIONAL and REQUIRED_INDEPENDENT security-attestation policies. The selected policy is immutable after registration."><div className="form-grid"><div className="field"><label htmlFor="register-target">Target address</label><input id="register-target" className="mono" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="0x…" /></div><div className="field"><label htmlFor="register-project">Project name</label><input id="register-project" value={project} onChange={(e) => setProject(e.target.value)} placeholder="Production application" /></div><div className="field span-2"><label htmlFor="register-source">Immutable current source URL</label><input id="register-source" className="mono" value={source} onChange={(e) => setSource(e.target.value)} placeholder="https://raw.githubusercontent.com/…/&lt;commit&gt;/contracts/…" /></div></div><div className="kv-grid" style={{ marginTop: 18 }}><KeyValue label="Target address valid">{isAddress(target) ? "yes" : "no"}</KeyValue><KeyValue label="Canonical governor">{config.governorAddress || "Deployment not configured"}</KeyValue><KeyValue label="Network">Studio-dev · 61997</KeyValue><KeyValue label="Registration path">Protected target → finalized governor child</KeyValue><KeyValue label="Security modes">OPTIONAL · REQUIRED_INDEPENDENT</KeyValue></div><Notice title="Canonical deployment not configured" tone="warning">This form does not create policy state and cannot bypass V2 target authorization. No historical profile address is substituted.</Notice><button className="button primary" style={{ marginTop: 18 }} disabled title="Canonical writes are disabled in Phase 2F"><LockKeyhole size={14} />Register protected contract</button></Card><div className="notice info" style={{ marginTop: 14 }}><ShieldPlus size={16} /><div><strong>No canonical registration has occurred</strong><div>SentinelX displays Deployment not configured until live V2 deployment is independently proven.</div></div></div></div>;
}
