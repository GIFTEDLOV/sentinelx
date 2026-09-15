import type { CalldataEncodable, Hash as GenLayerHash } from "genlayer-js/types";
import { isSuccessful } from "genlayer-js";
import { getGenLayerClient, getInjectedProvider } from "./client";
import { estimateWriteFees, feeEstimateToOptions } from "./fees";
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
    const receipt = await client.waitForTransactionReceipt({ hash: sdkHash(hash), waitUntil: "finalized", fullTransaction: true });
    const lifecycle = await getTransactionLifecycle(hash);
    const executionResult = receipt.txExecutionResultName;
    const successful = lifecycle.state === "finalized" && executionResult === "FINISHED_WITH_RETURN" && isSuccessful(receipt);
    const children = await client.getTriggeredTransactionIds({ hash: sdkHash(hash) });
    const record = updateTransaction(operation, {
      lifecycle,
      executionResult,
      childTransactionIds: children,
      verification: successful ? "successful" : "failed",
    });
    if (!record) throw new Error("transaction was not persisted before tracking");
    return record;
  } catch (error) {
    updateTransaction(operation, { verification: "ambiguous", lifecycle: { state: "unknown" } });
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
  const targetAddress = address(args.address);
  const quote = await estimateWriteFees({
    address: targetAddress,
    functionName: args.functionName,
    calldata: args.calldata,
    account: args.account,
    developmentSimulation: args.developmentSimulation,
  });
  const submittedAt = new Date().toISOString();
  const client = getGenLayerClient(provider, args.account);
  const hash = txHash(await client.writeContract({
    address: targetAddress,
    functionName: args.functionName,
    args: args.calldata as CalldataEncodable[] | undefined,
    // The SDK-returned complete fee object is carried unchanged into signing.
    // Gasless behavior is also estimator-driven: a zero quote is valid and is
    // encoded by the SDK without any network-name special case.
    fees: feeEstimateToOptions(quote.estimate),
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
