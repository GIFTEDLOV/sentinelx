"use client";

import { useQuery } from "@tanstack/react-query";
import { Radio } from "lucide-react";
import { getNetworkHealth } from "@/lib/genlayer/client";

export function NetworkIndicator() {
  const query = useQuery({ queryKey: ["network-health"], queryFn: getNetworkHealth, refetchInterval: 30_000 });
  const status = query.data?.status || "unavailable";
  const label = status === "healthy" ? "Studio-dev" : status === "wrong-network" ? "Wrong network" : "RPC unavailable";
  return <div className="network-indicator" title={query.data ? `${query.data.rpcUrl} · block ${query.data.blockNumber}` : "RPC health unavailable"}><span className={`network-dot ${status}`} /><span>{label}</span><span className="dim">61997</span><Radio size={13} /></div>;
}
