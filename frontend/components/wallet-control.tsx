"use client";

import { WalletCards } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { connectWallet, getInjectedProvider, getWalletChainId } from "@/lib/genlayer/client";
import { STUDIONET_CHAIN_ID } from "@/lib/genlayer/chains";
import { shortAddress } from "@/lib/workflow";

export function WalletControl() {
  const [state, setState] = useState<"disconnected" | "connecting" | "connected" | "wrong">("disconnected");
  const [address, setAddress] = useState<string>();
  const connect = async () => { setState("connecting"); try { const result = await connectWallet(); setAddress(result.address); setState(result.correctNetwork ? "connected" : "wrong"); if (!result.correctNetwork) toast.error("Switch wallet to Studionet · chain 61999"); } catch { setState("disconnected"); toast.error("Wallet connection was not completed."); } };
  useEffect(() => {
    const provider = getInjectedProvider();
    if (!provider?.on) return;
    const handleAccounts = (...args: unknown[]) => { const next = Array.isArray(args[0]) && typeof args[0][0] === "string" ? args[0][0] : undefined; setAddress(next); if (!next) setState("disconnected"); else void getWalletChainId(provider).then((chainId) => setState(chainId === STUDIONET_CHAIN_ID ? "connected" : "wrong")).catch(() => setState("disconnected")); };
    const handleChain = () => { if (address) void getWalletChainId(provider).then((chainId) => setState(chainId === STUDIONET_CHAIN_ID ? "connected" : "wrong")).catch(() => setState("disconnected")); };
    provider.on("accountsChanged", handleAccounts); provider.on("chainChanged", handleChain);
    return () => { provider.removeListener?.("accountsChanged", handleAccounts); provider.removeListener?.("chainChanged", handleChain); };
  }, [address]);
  if (state === "connected") return <button className="wallet connected" onClick={connect}><span className="wallet-dot" />{shortAddress(address)}</button>;
  if (state === "wrong") return <button className="wallet wrong" onClick={connect}><span className="wallet-dot" />Wrong network</button>;
  return <button className="wallet" onClick={connect} disabled={state === "connecting"}><span className="wallet-dot" />{state === "connecting" ? "Connecting…" : <><WalletCards size={14} />Connect wallet</>}</button>;
}
