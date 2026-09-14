"use client";

import { Activity, ChevronLeft, ChevronRight, FileText, FolderKanban, LayoutDashboard, Menu, PanelTop, Search, Settings2, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { CommandPalette } from "./command-palette";
import { NetworkIndicator } from "./network-indicator";
import { ThemeToggle } from "./theme-toggle";
import { TransactionCenter } from "./transaction-center";
import { WalletControl } from "./wallet-control";

const PRIMARY = [["Overview", "/app", LayoutDashboard], ["Projects", "/app/projects", FolderKanban], ["Releases", "/app/releases/new", ShieldCheck], ["Activity", "/app/activity", Activity]] as const;
const SECONDARY = [["Documentation", "https://github.com/GIFTEDLOV/sentinelx/tree/7e3b552c8b0471db0411206fdbc743dd12ef4e80/docs", FileText], ["Settings", "/app/settings", Settings2]] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname(); const [collapsed, setCollapsed] = useState(false); const [mobileOpen, setMobileOpen] = useState(false); const [commandOpen, setCommandOpen] = useState(false); const [txOpen, setTxOpen] = useState(false);
  const active = (href: string) => href === "/app" ? pathname === href : pathname.startsWith(href);
  return <div className="app-shell"><aside className={`sidebar ${collapsed ? "collapsed" : ""} ${mobileOpen ? "mobile-open" : ""}`}><div className="sidebar-header"><Link className="brand" href="/app" onClick={() => setMobileOpen(false)}><span className="brand-mark"><PanelTop size={14} /></span><span className="brand-word">SentinelX</span></Link><button className="sidebar-toggle" onClick={() => setCollapsed((v) => !v)} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>{collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}</button></div><nav className="nav-group" aria-label="Primary navigation">{PRIMARY.map(([label, href, Icon]) => <Link key={href} className={`nav-item ${active(href) ? "active" : ""}`} href={href} onClick={() => setMobileOpen(false)}><Icon size={16} /><span className="nav-label">{label}</span></Link>)}</nav><div className="sidebar-section">Workspace</div><nav className="nav-group" aria-label="Secondary navigation">{SECONDARY.map(([label, href, Icon]) => <Link key={href} className="nav-item" href={href} target={href.startsWith("http") ? "_blank" : undefined} onClick={() => setMobileOpen(false)}><Icon size={16} /><span className="nav-label">{label}</span></Link>)}</nav><div className="sidebar-bottom"><span className="network-dot" /> <span>Studio-dev · 61997</span></div></aside><div className="main-shell"><header className="topbar"><div className="topbar-context"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={17} /></button><NetworkIndicator /></div><div className="topbar-actions"><button className="search-trigger" onClick={() => setCommandOpen(true)}><Search size={14} />Search <span className="shortcut">⌘ K</span></button><button className="icon-button" aria-label="Open transaction center" onClick={() => setTxOpen(true)}><Activity size={16} /></button><ThemeToggle /><WalletControl /></div></header><main>{children}</main></div><CommandPalette open={commandOpen} onOpen={() => setCommandOpen(true)} onClose={() => setCommandOpen(false)} /><TransactionCenter open={txOpen} onClose={() => setTxOpen(false)} />{mobileOpen && <button className="drawer-backdrop" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><X size={0} /></button>}</div>;
}
