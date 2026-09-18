import { TransactionHashVariant } from "genlayer-js/types";
import type { CalldataEncodable, Hash as GenLayerHash } from "genlayer-js/types";
import { getGenLayerClient } from "./client";
import { getSentinelXConfig, isAddress } from "./chains";
import { GOVERNOR_METHODS, TARGET_METHODS } from "./contracts";
import type { EvidenceSnapshot, ReleaseProposal, TargetPolicy, TransactionLifecycle } from "./types";

function requireAddress(address: string | undefined, label: string): `0x${string}` {
  if (!isAddress(address)) throw new Error(`${label} is not configured`);
  return address;
}

function parseResult<T>(result: unknown): T {
  if (typeof result === "string") {
    try { return JSON.parse(result) as T; } catch { return result as T; }
  }
  return result as T;
}

async function read(address: `0x${string}`, functionName: string, args: unknown[] = []): Promise<unknown> {
  const client = getGenLayerClient();
  return client.readContract({
    address,
    functionName,
    args: args as CalldataEncodable[],
    transactionHashVariant: TransactionHashVariant.LATEST_FINAL,
    jsonSafeReturn: true,
  });
}

export async function getTargetPolicy(address?: string): Promise<TargetPolicy> {
  const governor = requireAddress(getSentinelXConfig().governorAddress, "SentinelX governor address");
  return parseResult<TargetPolicy>(await read(governor, GOVERNOR_METHODS.targetPolicy, [requireAddress(address, "target address")]));
}

export async function getTargetIds(): Promise<string[]> {
  const governor = requireAddress(getSentinelXConfig().governorAddress, "SentinelX governor address");
  const result = parseResult<unknown>(await read(governor, GOVERNOR_METHODS.targetIds));
  return Array.isArray(result) ? result.map(String) : [];
}

export async function getTargetProposals(address: string): Promise<number[]> {
  const governor = requireAddress(getSentinelXConfig().governorAddress, "SentinelX governor address");
  const result = parseResult<unknown>(await read(governor, GOVERNOR_METHODS.targetProposals, [requireAddress(address, "target address")]));
  return Array.isArray(result) ? result.map((value) => Number(value)) : [];
}

export async function getActiveProposal(address: string): Promise<number> {
  const governor = requireAddress(getSentinelXConfig().governorAddress, "SentinelX governor address");
  return Number(await read(governor, GOVERNOR_METHODS.activeProposal, [requireAddress(address, "target address")]));
}

export async function getProposal(id: number): Promise<ReleaseProposal> {
  const governor = requireAddress(getSentinelXConfig().governorAddress, "SentinelX governor address");
  return parseResult<ReleaseProposal>(await read(governor, GOVERNOR_METHODS.proposal, [BigInt(id)]));
}

export async function getProposalStatus(id: number): Promise<string> {
  const governor = requireAddress(getSentinelXConfig().governorAddress, "SentinelX governor address");
  return String(await read(governor, GOVERNOR_METHODS.proposalStatus, [BigInt(id)]));
}

export async function getEvidenceSnapshot(id: number): Promise<EvidenceSnapshot> {
  const governor = requireAddress(getSentinelXConfig().governorAddress, "SentinelX governor address");
  return parseResult<EvidenceSnapshot>(await read(governor, GOVERNOR_METHODS.evidenceSnapshot, [BigInt(id)]));
}

export async function getReviewWebFetchCount(id: number): Promise<number> {
  const governor = requireAddress(getSentinelXConfig().governorAddress, "SentinelX governor address");
  return Number(await read(governor, GOVERNOR_METHODS.reviewWebFetchCount, [BigInt(id)]));
}

export async function getReleaseHistory(address: string): Promise<number[]> {
  const governor = requireAddress(getSentinelXConfig().governorAddress, "SentinelX governor address");
  const result = parseResult<unknown>(await read(governor, GOVERNOR_METHODS.releaseHistory, [requireAddress(address, "target address")]));
  return Array.isArray(result) ? result.map(Number) : [];
}

export async function getGovernorInfo(): Promise<unknown> {
  const governor = requireAddress(getSentinelXConfig().governorAddress, "SentinelX governor address");
  return parseResult(await read(governor, GOVERNOR_METHODS.contractInfo));
}

export async function getTargetState(address?: string): Promise<Record<string, unknown>> {
  const target = requireAddress(address || getSentinelXConfig().canonicalTargetAddress, "target address");
  const values = await Promise.all([
    read(target, TARGET_METHODS.applicationName),
    read(target, TARGET_METHODS.owner),
    read(target, TARGET_METHODS.governor),
    read(target, TARGET_METHODS.registered),
    read(target, TARGET_METHODS.protectedValue),
    read(target, TARGET_METHODS.valueNonce),
    read(target, TARGET_METHODS.installedProposal),
    read(target, TARGET_METHODS.installedCandidateHash),
  ]);
  return {
    application_name: values[0], owner: values[1], governor: values[2],
    registered: values[3], protected_value: values[4], value_nonce: values[5],
    installed_proposal_id: values[6], installed_candidate_hash: values[7],
  };
}

export async function getTransactionLifecycle(hash: `0x${string}`): Promise<TransactionLifecycle> {
  const transaction = await getGenLayerClient().getTransaction({ hash: hash as GenLayerHash });
  const status = String(transaction.statusName || transaction.status || "");
  const state = status === "FINALIZED" ? "finalized" :
    status === "ACCEPTED" ? "decided" :
      status === "CANCELED" ? "canceled" : "processing";
  return {
    state,
    storedStatus: status,
    projectedStatus: status,
  };
}
