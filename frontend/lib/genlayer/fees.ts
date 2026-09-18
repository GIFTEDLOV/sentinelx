import { getGenLayerClient } from "./client";
import { getRpcUrl, STUDIONET_CHAIN_ID } from "./chains";

/** Stable genlayer-js 1.1.x records native gas observations, not the RC fee wire object. */
export interface MeasuredFeeEntry {
  gasUsed: string;
  transactionValue: string;
}

export interface MeasuredFeeProfile {
  version: 1;
  network: "studionet";
  chainId: 61999;
  measuredAt: string;
  deploy?: MeasuredFeeEntry;
  methods: Record<string, MeasuredFeeEntry>;
}

function validEntry(entry: unknown): entry is MeasuredFeeEntry {
  if (!entry || typeof entry !== "object") return false;
  const value = entry as Record<string, unknown>;
  return typeof value.gasUsed === "string" && /^\d+$/.test(value.gasUsed) &&
    typeof value.transactionValue === "string" && /^\d+$/.test(value.transactionValue);
}

export function validateFeeProfile(value: unknown): MeasuredFeeProfile {
  if (!value || typeof value !== "object") throw new Error("fee profile is not an object");
  const profile = value as Partial<MeasuredFeeProfile>;
  if (profile.version !== 1 || profile.network !== "studionet" || profile.chainId !== STUDIONET_CHAIN_ID) {
    throw new Error("fee profile is not for Studionet chain 61999");
  }
  if (!profile.methods || typeof profile.methods !== "object") throw new Error("fee profile methods are missing");
  if (profile.deploy && !validEntry(profile.deploy)) throw new Error("invalid deploy fee entry");
  for (const [method, entry] of Object.entries(profile.methods)) {
    if (!validEntry(entry)) throw new Error(`invalid measured stable gas entry ${method}`);
  }
  return profile as MeasuredFeeProfile;
}

export async function loadMeasuredFeeProfile(): Promise<MeasuredFeeProfile> {
  const url = process.env.NEXT_PUBLIC_SENTINELX_FEE_PROFILE_URL;
  if (!url) throw new Error("No measured fee profile is configured");
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`fee profile unavailable (${response.status})`);
  return validateFeeProfile(await response.json());
}

export async function loadMeasuredFeeProfileIfConfigured(): Promise<MeasuredFeeProfile | undefined> {
  if (!process.env.NEXT_PUBLIC_SENTINELX_FEE_PROFILE_URL) return undefined;
  return loadMeasuredFeeProfile();
}

export type FeeQuoteSource = "stable-sdk-native";

export interface FeeQuote {
  source: FeeQuoteSource;
  gasless: false;
}

/**
 * genlayer-js 1.1.8 owns the native gas estimate inside writeContract. No RC
 * fee distribution, feeValue, or guessed quantity is manufactured here.
 */
export async function estimateWriteFees(args: {
  address: `0x${string}`;
  functionName: string;
  calldata?: unknown[];
  account?: `0x${string}`;
}): Promise<FeeQuote> {
  if (!args.account) throw new Error("stable write estimation requires an account");
  const client = getGenLayerClient(undefined, args.account);
  await client.estimateTransactionGas({
    from: args.account,
    to: args.address,
    value: BigInt(0),
  });
  return { source: "stable-sdk-native", gasless: false };
}

export function feeConfigurationSummary(): { configured: boolean; rpcUrl: string; chainId: number } {
  return {
    configured: Boolean(process.env.NEXT_PUBLIC_SENTINELX_FEE_PROFILE_URL),
    rpcUrl: getRpcUrl(),
    chainId: STUDIONET_CHAIN_ID,
  };
}
