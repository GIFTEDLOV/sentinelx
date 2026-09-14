"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

export function CopyButton({ value, label = "Copy value" }: { value?: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return <button className="copy-button" aria-label={label} disabled={!value} onClick={async () => { if (!value) return; await navigator.clipboard.writeText(value); setCopied(true); toast.success("Copied"); window.setTimeout(() => setCopied(false), 1200); }}>{copied ? <Check size={13} /> : <Copy size={13} />}</button>;
}
