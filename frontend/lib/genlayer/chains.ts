import { studioDevnet } from "genlayer-js/chains";
import type { SentinelXConfig } from "./types";

export const STUDIO_DEV_RPC = "https://studio-dev.genlayer.com/api";
export const STUDIO_DEV_CHAIN_ID = 61997;
export const STUDIO_DEV_NAME = "studio-dev";

export function getRpcUrl(): string {
  return process.env.NEXT_PUBLIC_GENLAYER_RPC_URL?.trim() || STUDIO_DEV_RPC;
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
  return {
    rpcUrl,
    chainId: STUDIO_DEV_CHAIN_ID,
    governorAddress: addressesValid ? governorAddress : undefined,
    canonicalTargetAddress: addressesValid ? canonicalTargetAddress : undefined,
    feeProfileUrl: process.env.NEXT_PUBLIC_SENTINELX_FEE_PROFILE_URL?.trim() || undefined,
    status: addressesValid && governorAddress && canonicalTargetAddress ? "configured" : "unconfigured",
  };
}

export function getStudioDevChain() {
  if (studioDevnet.id !== STUDIO_DEV_CHAIN_ID) {
    throw new Error("GenLayerJS studioDevnet does not match chain 61997");
  }
  return studioDevnet;
}

export function previewEnabled(): boolean {
  return process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_SENTINELX_PREVIEW === "true";
}
