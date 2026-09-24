import { createClient } from "genlayer-js";
import type { SentinelXConfig } from "./types";
import { getBrowserRpcEndpoint, getRpcUrl, getSentinelXConfig, getStudionetChain, STUDIONET_CHAIN_ID, STUDIONET_NAME } from "./chains";

export interface Eip1193Provider {
  request(args: { method: string; params?: unknown[] }): Promise<unknown>;
  on?: (event: string, listener: (...args: unknown[]) => void) => void;
  removeListener?: (event: string, listener: (...args: unknown[]) => void) => void;
}

declare global {
  interface Window {
    ethereum?: Eip1193Provider;
  }
}

export function getInjectedProvider(): Eip1193Provider | undefined {
  return typeof window === "undefined" ? undefined : window.ethereum;
}

export function getGenLayerClient(provider?: Eip1193Provider, account?: `0x${string}`) {
  const config = {
    chain: getStudionetChain(),
    endpoint: getBrowserRpcEndpoint(),
    ...(account ? { account } : {}),
    ...(provider ? { provider: provider as never } : {}),
  };
  return createClient(config);
}

export async function getNetworkHealth(): Promise<{
  name: string;
  chainId: number;
  rpcUrl: string;
  blockNumber: string;
  status: "healthy" | "wrong-network" | "unavailable";
}> {
  const client = getGenLayerClient();
  try {
    const chainId = await client.getChainId();
    const blockNumber = await client.getBlockNumber();
    return {
      name: STUDIONET_NAME,
      chainId,
      rpcUrl: getRpcUrl(),
      blockNumber: blockNumber.toString(),
      status: chainId === STUDIONET_CHAIN_ID ? "healthy" : "wrong-network",
    };
    } catch {
    return {
      name: STUDIONET_NAME,
      chainId: STUDIONET_CHAIN_ID,
      rpcUrl: getRpcUrl(),
      blockNumber: "UNAVAILABLE",
      status: "unavailable",
    };
  }
}

export async function getWalletChainId(provider: Eip1193Provider): Promise<number | undefined> {
  const result = await provider.request({ method: "eth_chainId" });
  if (typeof result !== "string") return undefined;
  return Number.parseInt(result, 16);
}

export async function connectWallet(): Promise<{ address: string; chainId?: number; correctNetwork: boolean }> {
  const provider = getInjectedProvider();
  if (!provider) throw new Error("No browser wallet provider detected");
  const result = await provider.request({ method: "eth_requestAccounts" });
  const accounts = Array.isArray(result) ? result : [];
  const address = typeof accounts[0] === "string" ? accounts[0] : "";
  if (!address) throw new Error("Wallet returned no account");
  const chainId = await getWalletChainId(provider);
  return { address, chainId, correctNetwork: chainId === STUDIONET_CHAIN_ID };
}

export function configurationSummary(): SentinelXConfig {
  return getSentinelXConfig();
}
