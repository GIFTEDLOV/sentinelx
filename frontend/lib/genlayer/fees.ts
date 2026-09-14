import type { CalldataEncodable, FeeEstimateOptions, TransactionFeeEstimate, TransactionFeeOptions } from "genlayer-js/types";
import { getGenLayerClient, getInjectedProvider } from "./client";
import { getRpcUrl, STUDIO_DEV_CHAIN_ID } from "./chains";

export interface MeasuredFeeEntry {
  leaderTimeunitsAllocation: string;
  validatorTimeunitsAllocation: string;
  executionBudgetPerRound: string;
  totalMessageFees: string;
  rotationsPerRound: string;
}

export interface MeasuredFeeProfile {
  version: 1;
  network: "studio_devnet";
  chainId: 61997;
  measuredAt: string;
  deploy: MeasuredFeeEntry;
  methods: Record<string, MeasuredFeeEntry>;
}

const REQUIRED_METHODS = [
  "register_with_sentinelx", "register_target", "create_proposal", "review_proposal",
  "repair_evidence", "retry_review", "cancel_proposal", "expire_proposal",
  "reconcile_install", "mark_execution_timeout", "confirm_install", "install_reviewed_upgrade",
] as const;

function uint(value: string, label: string): number {
  if (!/^\d+$/.test(value)) throw new Error(`${label} is not an unsigned decimal quantity`);
  return Number(value);
}

function validEntry(entry: unknown): entry is MeasuredFeeEntry {
  if (!entry || typeof entry !== "object") return false;
  return (["leaderTimeunitsAllocation", "validatorTimeunitsAllocation", "executionBudgetPerRound", "totalMessageFees", "rotationsPerRound"] as const).every((field) => typeof (entry as Record<string, unknown>)[field] === "string" && /^\d+$/.test((entry as Record<string, string>)[field]));
}

export function profileEntryToOptions(entry: MeasuredFeeEntry, appealRounds = 1): FeeEstimateOptions {
  return {
    leaderTimeunitsAllocation: uint(entry.leaderTimeunitsAllocation, "leaderTimeunitsAllocation"),
    validatorTimeunitsAllocation: uint(entry.validatorTimeunitsAllocation, "validatorTimeunitsAllocation"),
    appealRounds,
    executionBudgetPerRound: uint(entry.executionBudgetPerRound, "executionBudgetPerRound"),
    totalMessageFees: uint(entry.totalMessageFees, "totalMessageFees"),
    rotations: Array.from({ length: appealRounds + 1 }, () => uint(entry.rotationsPerRound, "rotationsPerRound")),
  };
}

export function validateFeeProfile(value: unknown): MeasuredFeeProfile {
  if (!value || typeof value !== "object") throw new Error("fee profile is not an object");
  const profile = value as Partial<MeasuredFeeProfile>;
  if (profile.version !== 1 || profile.network !== "studio_devnet" || profile.chainId !== STUDIO_DEV_CHAIN_ID) {
    throw new Error("fee profile is not for Studio-dev chain 61997");
  }
  if (!profile.deploy || !profile.methods) throw new Error("fee profile is incomplete");
  if (!validEntry(profile.deploy)) throw new Error("invalid deploy fee entry");
  for (const method of REQUIRED_METHODS) {
    if (!validEntry(profile.methods[method])) throw new Error(`missing or invalid measured fee operation ${method}`);
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

export async function estimateWriteFees(args: {
  address: `0x${string}`;
  functionName: string;
  calldata?: unknown[];
  account?: `0x${string}`;
  appealRounds?: number;
}): Promise<TransactionFeeEstimate> {
  const profile = await loadMeasuredFeeProfile();
  const entry = profile.methods[args.functionName];
  if (!entry) throw new Error(`no measured fee entry for ${args.functionName}`);
  return getGenLayerClient(getInjectedProvider(), args.account).estimateTransactionFeesForWrite({
    address: args.address,
    functionName: args.functionName,
    args: args.calldata as CalldataEncodable[] | undefined,
    ...profileEntryToOptions(entry, args.appealRounds),
  });
}

export function feeEstimateToOptions(estimate: TransactionFeeEstimate): TransactionFeeOptions {
  return {
    distribution: estimate.distribution,
    ...(estimate.messageAllocations ? { messageAllocations: estimate.messageAllocations } : {}),
    feeValue: estimate.feeValue,
  };
}

export function feeConfigurationSummary(): { configured: boolean; rpcUrl: string; chainId: number } {
  return {
    configured: Boolean(process.env.NEXT_PUBLIC_SENTINELX_FEE_PROFILE_URL),
    rpcUrl: getRpcUrl(),
    chainId: STUDIO_DEV_CHAIN_ID,
  };
}
