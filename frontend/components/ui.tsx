import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowRight, Inbox, ShieldAlert } from "lucide-react";
import { shortHash } from "@/lib/workflow";

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <div className="page-header"><div><div className="section-kicker">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="page-actions">{actions}</div>}</div>;
}

export function Card({ children, className = "", title, subtitle, action }: { children: ReactNode; className?: string; title?: string; subtitle?: string; action?: ReactNode }) {
  return <section className={`card ${className}`}>{title ? <div className="card-header"><div><h2 className="card-title">{title}</h2>{subtitle && <p className="card-subtitle">{subtitle}</p>}</div>{action}</div> : null}{title ? <div className="card-pad">{children}</div> : children}</section>;
}

export function StatCard({ label, value, note, tone }: { label: string; value: ReactNode; note?: string; tone?: "green" | "amber" | "red" }) {
  return <div className="card stat-card"><div className="stat-label">{label}</div><div className={`stat-value ${tone ? `tone-${tone}` : ""}`}>{value}</div>{note && <div className="stat-note">{note}</div>}</div>;
}

export function StatusBadge({ value, tone }: { value: string; tone?: "verified" | "waiting" | "rejected" | "neutral" | "info" | "pass" | "failed" | "missing" | "not-reviewed" | "unverified" | "successful" | "pending" }) {
  const inferred = tone || (/(VERIFIED|PASS|SUCCESS|FINISHED)/i.test(value) ? "verified" : /(REJECT|FAIL|ERROR|MISSING)/i.test(value) ? "rejected" : /(WAIT|PROPOS|REVIEW|ACCEPT|PENDING|QUEUED)/i.test(value) ? "waiting" : "neutral");
  return <span className={`status ${inferred}`}>{value.replaceAll("_", " ")}</span>;
}

export function CopyText({ value, mono = true }: { value?: string; mono?: boolean }) {
  return <span className="copy-line"><span className={mono ? "mono" : ""} title={value}>{shortHash(value)}</span></span>;
}

export function LoadingCard({ rows = 4 }: { rows?: number }) {
  return <div className="card card-pad page-grid">{Array.from({ length: rows }, (_, index) => <div key={index} className="skeleton" style={{ width: `${75 - index * 8}%` }} />)}</div>;
}

export function Skeleton({ width = "100%", height = 14 }: { width?: string | number; height?: string | number }) {
  return <div className="skeleton" style={{ width, height }} />;
}

export function EmptyState({ title, description, action, icon }: { title: string; description: string; action?: ReactNode; icon?: ReactNode }) {
  return <div className="empty"> <div className="empty-icon">{icon || <Inbox size={19} />}</div><h3>{title}</h3><p>{description}</p>{action}</div>;
}

export function ErrorState({ title = "Chain data unavailable", description, retry }: { title?: string; description: string; retry?: () => void }) {
  return <div className="empty"><div className="empty-icon"><ShieldAlert size={19} /></div><h3>{title}</h3><p>{description}</p>{retry && <button className="button ghost" onClick={retry}>Try again <ArrowRight size={14} /></button>}</div>;
}

export function Notice({ title, children, tone = "info" }: { title: string; children: ReactNode; tone?: "warning" | "error" | "info" }) {
  return <div className={`notice ${tone}`}><div><strong>{title}</strong><div>{children}</div></div></div>;
}

export function Tabs({ items, active }: { items: Array<{ label: string; href: string }>; active: string }) {
  return <nav className="tabs" aria-label="Section navigation">{items.map((item) => <Link key={item.href} className={`tab ${active === item.label ? "active" : ""}`} href={item.href}>{item.label}</Link>)}</nav>;
}

export function KeyValue({ label, children, mono = false }: { label: string; children: ReactNode; mono?: boolean }) {
  return <div className="kv"><div className="kv-label">{label}</div><div className={`kv-value ${mono ? "mono" : ""}`}>{children}</div></div>;
}

export function PreviewRibbon() { return <div className="preview-ribbon">Preview fixtures · no chain state</div>; }
