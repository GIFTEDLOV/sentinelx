"use client";

import { Command, FileCode2, FolderKanban, LayoutDashboard, Search, Settings2, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

const ITEMS = [
  ["Overview", "/app", LayoutDashboard], ["Projects", "/app/projects", FolderKanban], ["New release", "/app/releases/new", ShieldCheck], ["Activity", "/app/activity", Command], ["Architecture", "https://github.com/GIFTEDLOV/sentinelx/blob/main/docs/ARCHITECTURE.md", FileCode2], ["Settings", "/app/settings", Settings2],
] as const;

export function CommandPalette({ open, onOpen, onClose }: { open: boolean; onOpen: () => void; onClose: () => void }) {
  const [filter, setFilter] = useState("");
  useEffect(() => { const handler = (event: KeyboardEvent) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); onOpen(); } if (event.key === "Escape") onClose(); }; window.addEventListener("keydown", handler); return () => window.removeEventListener("keydown", handler); }, [onClose, onOpen]);
  if (!open) return null;
  const items = ITEMS.filter(([label]) => label.toLowerCase().includes(filter.toLowerCase()));
  return <div className="command-backdrop" role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}><div className="command"><div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 10px" }}><Search size={15} className="dim" /><input autoFocus className="command-input" placeholder="Search SentinelX…" value={filter} onChange={(e) => setFilter(e.target.value)} /><button className="icon-button" onClick={onClose} aria-label="Close command palette"><X size={14} /></button></div><div className="command-list">{items.length ? items.map(([label, href, Icon]) => <Link className="command-item" key={label} href={href} onClick={onClose}><Icon size={15} />{label}<span className="dim" style={{ marginLeft: "auto" }}>↵</span></Link>) : <div className="command-empty">No matching commands.</div>}</div></div></div>;
}
