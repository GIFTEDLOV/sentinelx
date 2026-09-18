import type { CalldataEncodable, Hash as GenLayerHash } from "genlayer-js/types";
import { TransactionStatus } from "genlayer-js/types";
import { getGenLayerClient, getInjectedProvider, getWalletChainId } from "./client";
import { getSentinelXConfig, STUDIONET_CHAIN_ID } from "./chains";
import { estimateWriteFees } from "./fees";
import { getTransactionLifecycle } from "./reads";
import { saveTransaction, updateTransaction } from "./transactions";
import type { TransactionRecord } from "./types";

function address(value: string): `0x${string}` {
  if (!/^0x[0-9a-fA-F]{40}$/.test(value)) throw new Error("invalid contract address");
  return value as `0x${string}`;
}

function txHash(value: unknown): `0x${string}` {
  if (typeof value !== "string" || !/^0x[0-9a-fA-F]{64}$/.test(value)) {
    throw new Error("SDK did not return a valid transaction hash");
  }
  return value.toLowerCase() as `0x${string}`;
}

function sdkHash(value: `0x${string}`): GenLayerHash {
  return value as GenLayerHash;
}

export async function trackTransaction(operation: string, hash: `0x${string}`): Promise<TransactionRecord> {
  const client = getGenLayerClient(getInjectedProvider());
  try {
    const receipt = await client.waitForTransactionReceipt({ hash: sdkHash(hash), status: TransactionStatus.FINALIZED });
    const lifecycle = await getTransactionLifecycle(hash);
    const executionResult = receipt.txExecutionResultName;
    const successful = lifecycle.state === "finalized" && executionResult === "FINISHED_WITH_RETURN";
    const children = await client.getTriggeredTransactionIds({ hash: sdkHash(hash) });
    const record = updateTransaction(hash, {
      lifecycle,
      executionResult,
      childTransactionIds: children,
      verification: successful ? "successful" : "failed",
    });
    if (!record) throw new Error("transaction was not persisted before tracking");
    return record;
  } catch (error) {
    updateTransaction(hash, { verification: "ambiguous", lifecycle: { state: "unknown" } });
    throw new Error(`Polling failed for ${hash}; resume tracking the same hash. ${String(error)}`);
  }
}

export async function writeContractOnce(args: {
  operation: string;
  address: string;
  functionName: string;
  calldata?: unknown[];
  account: `0x${string}`;
  target?: string;
  proposalId?: number;
  developmentSimulation?: boolean;
}): Promise<TransactionRecord> {
  const provider = getInjectedProvider();
  if (!provider) throw new Error("Connect a browser wallet before writing");
  if (getSentinelXConfig().status !== "configured") throw new Error("Canonical Studionet configuration is unavailable");
  if (await getWalletChainId(provider) !== STUDIONET_CHAIN_ID) throw new Error("Switch the wallet to Studionet before writing");
  const targetAddress = address(args.address);
  await estimateWriteFees({
    address: targetAddress,
    functionName: args.functionName,
    calldata: args.calldata,
    account: args.account,
  });
  const submittedAt = new Date().toISOString();
  const client = getGenLayerClient(provider, args.account);
  const hash = txHash(await client.writeContract({
    address: targetAddress,
    functionName: args.functionName,
    args: args.calldata as CalldataEncodable[] | undefined,
    // Stable genlayer-js 1.1.8 performs its native gas estimation inside
    // writeContract. The explicit preflight quote above is retained for
    // operator visibility; no RC fee object is passed to the stable SDK.
    value: BigInt(0),
  }));
  // This is deliberately the first operation after the SDK returns a hash.
  saveTransaction({
    operation: args.operation,
    hash,
    target: args.target || args.address,
    proposalId: args.proposalId,
    submittedAt,
    lifecycle: { state: "processing" },
    childTransactionIds: [],
    verification: "pending",
  });
  return trackTransaction(args.operation, hash);
}

export async function finalizeDecisionOnce(args: {
  operation: string;
  hash: `0x${string}`;
  account: `0x${string}`;
}): Promise<`0x${string}`> {
  const lifecycle = await getTransactionLifecycle(args.hash);
  if (lifecycle.resolutionAction !== "Finalize" || !lifecycle.decisionActive || !lifecycle.decisionId) {
    throw new Error("Finalize is unavailable without the current active decision identity");
  }
  const client = getGenLayerClient(getInjectedProvider(), args.account);
  const returned = await client.finalizeTransaction({ txId: args.hash });
  const hash = txHash(returned);
  saveTransaction({
    operation: `${args.operation}.finalize.decision-${lifecycle.decisionId}`,
    hash,
    submittedAt: new Date().toISOString(),
    lifecycle: { state: "processing", decisionId: lifecycle.decisionId, decisionActive: true },
    childTransactionIds: [],
    verification: "pending",
  });
  return hash;
}
