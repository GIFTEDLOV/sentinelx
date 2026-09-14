"use client";

import { WalletCards } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { connectWallet, getInjectedProvider } from "@/lib/genlayer/client";
import { shortAddress } from "@/lib/workflow";

export function WalletControl() {
  const [state, setState] = useState<"disconnected" | "connecting" | "connected" | "wrong">("disconnected");
  const [address, setAddress] = useState<string>();
  const connect = async () => { setState("connecting"); try { const result = await connectWallet(); setAddress(result.address); setState(result.correctNetwork ? "connected" : "wrong"); if (!result.correctNetwork) toast.error("Switch wallet to Studio-dev · chain 61997"); } catch (error) { setState("disconnected"); toast.error(String(error)); } };
  useEffect(() => {
    const provider = getInjectedProvider();
    if (!provider?.on) return;
    const handleAccounts = (...args: unknown[]) => { const next = Array.isArray(args[0]) && typeof args[0][0] === "string" ? args[0][0] : undefined; setAddress(next); if (!next) setState("disconnected"); };
    const handleChain = () => { void connect(); };
    provider.on("accountsChanged", handleAccounts); provider.on("chainChanged", handleChain);
    return () => { provider.removeListener?.("accountsChanged", handleAccounts); provider.removeListener?.("chainChanged", handleChain); };
  }, []);
  if (state === "connected") return <button className="wallet connected" onClick={connect}><span className="wallet-dot" />{shortAddress(address)}</button>;
  if (state === "wrong") return <button className="wallet wrong" onClick={connect}><span className="wallet-dot" />Wrong network</button>;
  return <button className="wallet" onClick={connect} disabled={state === "connecting"}><span className="wallet-dot" />{state === "connecting" ? "Connecting…" : <><WalletCards size={14} />Connect wallet</>}</button>;
}
