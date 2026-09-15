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
  deploy?: MeasuredFeeEntry;
  methods: Record<string, MeasuredFeeEntry>;
}

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
  if (!profile.methods || typeof profile.methods !== "object") throw new Error("fee profile methods are missing");
  if (profile.deploy && !validEntry(profile.deploy)) throw new Error("invalid deploy fee entry");
  for (const [method, entry] of Object.entries(profile.methods)) {
    if (!validEntry(entry)) throw new Error(`invalid measured fee operation ${method}`);
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

/** Missing profile coverage is allowed; malformed configured profiles still fail closed. */
export async function loadMeasuredFeeProfileIfConfigured(): Promise<MeasuredFeeProfile | undefined> {
  if (!process.env.NEXT_PUBLIC_SENTINELX_FEE_PROFILE_URL) return undefined;
  return loadMeasuredFeeProfile();
}

export type FeeQuoteSource = "measured-profile" | "network-default" | "write-simulation";

export interface FeeQuote {
  estimate: TransactionFeeEstimate;
  source: FeeQuoteSource;
  gasless: boolean;
}

function samePolicy(left: TransactionFeeEstimate["policy"], right: TransactionFeeEstimate["policy"]): boolean {
  return left.enabled === right.enabled &&
    left.genPerTimeUnit === right.genPerTimeUnit &&
    left.storageUnitPrice === right.storageUnitPrice &&
    left.receiptGasPrice === right.receiptGasPrice &&
    left.executionBudgetFloor === right.executionBudgetFloor &&
    left.timeUnitOverlayBps === right.timeUnitOverlayBps;
}

/** Gasless is a live estimator result, never a network-name assumption. */
export function isGaslessFeeEstimate(estimate: TransactionFeeEstimate): boolean {
  return estimate.policy.enabled === false || estimate.feeValue === BigInt(0);
}

function assertPolicyMatch(expected: TransactionFeeEstimate["policy"], estimate: TransactionFeeEstimate): void {
  if (!samePolicy(expected, estimate.policy)) {
    throw new Error("live fee policy changed during estimation; signing is blocked and the transaction must be re-estimated");
  }
}

async function estimateWithPolicyCheck(
  client: ReturnType<typeof getGenLayerClient>,
  estimate: () => Promise<TransactionFeeEstimate>,
): Promise<TransactionFeeEstimate> {
  const policyBefore = await client.getCurrentFeePolicy();
  const first = await estimate();
  if (samePolicy(policyBefore, first.policy)) return first;

  // A changed policy is never silently accepted. Re-estimate once against the
  // new live policy, then fail closed if it moves again.
  const policyBeforeRetry = await client.getCurrentFeePolicy();
  const retry = await estimate();
  assertPolicyMatch(policyBeforeRetry, retry);
  return retry;
}

export async function estimateWriteFees(args: {
  address: `0x${string}`;
  functionName: string;
  calldata?: unknown[];
  account?: `0x${string}`;
  appealRounds?: number;
  /** Explicit development/profiling escape hatch for one concrete write. */
  developmentSimulation?: boolean;
}): Promise<FeeQuote> {
  const client = getGenLayerClient(getInjectedProvider(), args.account);
  const profile = await loadMeasuredFeeProfileIfConfigured();
  const entry = profile?.methods[args.functionName];
  const useSimulation = args.developmentSimulation === true || process.env.NEXT_PUBLIC_SENTINELX_WRITE_SIMULATION === "true";

  if (entry) {
    const estimate = await estimateWithPolicyCheck(client, () => client.estimateTransactionFeesForWrite({
      address: args.address,
      functionName: args.functionName,
      args: args.calldata as CalldataEncodable[] | undefined,
      ...profileEntryToOptions(entry, args.appealRounds),
    }));
    return { estimate, source: "measured-profile", gasless: isGaslessFeeEstimate(estimate) };
  }

  if (useSimulation) {
    const estimate = await estimateWithPolicyCheck(client, () => client.estimateTransactionFeesForWrite({
      address: args.address,
      functionName: args.functionName,
      args: args.calldata as CalldataEncodable[] | undefined,
      appealRounds: args.appealRounds,
    }));
    return { estimate, source: "write-simulation", gasless: isGaslessFeeEstimate(estimate) };
  }

  // genlayer-js delegates this to the current Studio/network policy. It is a
  // complete fee object and does not require a developer fee-profile entry.
  const estimate = await estimateWithPolicyCheck(client, () => client.estimateTransactionFees({
    appealRounds: args.appealRounds,
  }));
  return { estimate, source: "network-default", gasless: isGaslessFeeEstimate(estimate) };
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
