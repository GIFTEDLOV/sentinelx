"use client";

import { Activity, RefreshCw, X } from "lucide-react";
import { useSyncExternalStore } from "react";
import { toast } from "sonner";
import { getInjectedProvider } from "@/lib/genlayer/client";
import { trackTransaction } from "@/lib/genlayer/writes";
import { listTransactions } from "@/lib/genlayer/transactions";
import { shortHash } from "@/lib/workflow";
import { StatusBadge } from "./ui";

export function TransactionCenter({ open, onClose }: { open: boolean; onClose: () => void }) {
  const subscribe = (callback: () => void) => { window.addEventListener("sentinelx:transactions", callback); return () => window.removeEventListener("sentinelx:transactions", callback); };
  const records = useSyncExternalStore(subscribe, listTransactions, () => []);
  if (!open) return null;
  return <><div className="drawer-backdrop" onClick={onClose} /><aside className="drawer" aria-label="Transaction center"><div className="drawer-header"><div><div className="section-kicker">Operations</div><h2 className="card-title">Transaction center</h2></div><button className="icon-button" aria-label="Close transaction center" onClick={onClose}><X size={15} /></button></div>{records.length === 0 ? <div className="empty"><div className="empty-icon"><Activity size={18} /></div><h3>No tracked transactions</h3><p>Returned hashes are persisted before lifecycle tracking begins.</p></div> : records.map((record) => <div className="transaction-item" key={`${record.operation}-${record.hash}`}><div className="transaction-top"><span className="transaction-operation">{record.operation}</span><StatusBadge value={record.verification} /></div><span className="transaction-hash" title={record.hash}>{shortHash(record.hash, 13)}</span><span className="dim">{record.lifecycle.state}{record.executionResult ? ` · ${record.executionResult}` : ""}</span>{record.verification === "ambiguous" && <button className="button ghost" onClick={async () => { if (!getInjectedProvider()) { toast.error("Connect the wallet to resume tracking"); return; } try { await trackTransaction(record.operation, record.hash as `0x${string}`); toast.success("Tracking updated"); } catch (error) { toast.error(String(error)); } }}><RefreshCw size={13} />Resume tracking</button>}</div>)}</aside></>;
}
