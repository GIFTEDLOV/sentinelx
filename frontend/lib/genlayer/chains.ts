import { studionet } from "genlayer-js/chains";
import type { SentinelXConfig } from "./types";

export const STUDIONET_RPC = "https://studio.genlayer.com/api";
export const STUDIONET_CHAIN_ID = 61999;
export const STUDIONET_NAME = "Studionet";
export const CANONICAL_GOVERNOR = "0xb28b8E7F8930b4bd7Ed8572dA7e51AA4ca9D7cA8";
export const CANONICAL_TARGET = "0xaF9ABA4DD9869d5F92EeA92c700E5f09A6978e21";

export function getRpcUrl(): string {
  return process.env.NEXT_PUBLIC_GENLAYER_RPC_URL?.trim() || STUDIONET_RPC;
}

/**
 * Browser reads use the same-origin proxy so stable Studionet RPC calls do not
 * depend on the upstream endpoint exposing browser CORS headers. The displayed
 * and validated network identity remains the canonical Studionet RPC above.
 */
export function getBrowserRpcEndpoint(): string {
  return typeof window === "undefined" ? getRpcUrl() : "/api/genlayer";
}

export function isAddress(value: string | undefined): value is `0x${string}` {
  return Boolean(value && /^0x[0-9a-fA-F]{40}$/.test(value));
}

export function getSentinelXConfig(): SentinelXConfig {
  const governorAddress = process.env.NEXT_PUBLIC_SENTINELX_GOVERNOR_ADDRESS?.trim() || undefined;
  const canonicalTargetAddress = process.env.NEXT_PUBLIC_SENTINELX_CANONICAL_TARGET_ADDRESS?.trim() || undefined;
  const rpcUrl = getRpcUrl();
  const addressesValid = (!governorAddress || isAddress(governorAddress)) &&
    (!canonicalTargetAddress || isAddress(canonicalTargetAddress));
  const rpcValid = rpcUrl === STUDIONET_RPC;
  const productionAddressesValid = process.env.NODE_ENV !== "production" ||
    (governorAddress === CANONICAL_GOVERNOR && canonicalTargetAddress === CANONICAL_TARGET);
  return {
    rpcUrl,
    chainId: STUDIONET_CHAIN_ID,
    governorAddress: addressesValid ? governorAddress : undefined,
    canonicalTargetAddress: addressesValid ? canonicalTargetAddress : undefined,
    feeProfileUrl: process.env.NEXT_PUBLIC_SENTINELX_FEE_PROFILE_URL?.trim() || undefined,
    status: !rpcValid ? "wrong-network" : addressesValid && productionAddressesValid && governorAddress && canonicalTargetAddress ? "configured" : "unconfigured",
  };
}

export function getStudionetChain() {
  if (studionet.id !== STUDIONET_CHAIN_ID) {
    throw new Error("GenLayerJS studionet does not match chain 61999");
  }
  return studionet;
}

export function previewEnabled(): boolean {
  return process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_SENTINELX_PREVIEW === "true";
}
