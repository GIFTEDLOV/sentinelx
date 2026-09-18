import type { TransactionRecord } from "./types";

const STORAGE_KEY = "sentinelx.transaction-center.v1";
export const TRANSACTION_EVENT = "sentinelx:transactions";

const EMPTY_TRANSACTIONS: readonly TransactionRecord[] = Object.freeze([]);
let snapshotInitialized = false;
let snapshotRaw: string | null = null;
let snapshot: readonly TransactionRecord[] = EMPTY_TRANSACTIONS;
const listeners = new Set<() => void>();

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function normalizeRecord(value: unknown): TransactionRecord | undefined {
  if (!isRecord(value)) return undefined;
  const lifecycle = isRecord(value.lifecycle) ? value.lifecycle : undefined;
  const hash = typeof value.hash === "string" ? value.hash : "";
  const operation = typeof value.operation === "string" ? value.operation.trim() : "";
  const childTransactionIds = Array.isArray(value.childTransactionIds)
    ? value.childTransactionIds.filter((child): child is string => typeof child === "string")
    : [];
  const verification = value.verification;
  const lifecycleState = lifecycle?.state;
  if (!operation || !/^0x[0-9a-fA-F]{64}$/.test(hash) || !lifecycle ||
      !["processing", "decided", "finalized", "canceled", "unknown"].includes(String(lifecycleState)) ||
      !["pending", "finalized", "successful", "failed", "ambiguous"].includes(String(verification))) {
    return undefined;
  }
  return {
    operation,
    hash: hash.toLowerCase(),
    ...(typeof value.target === "string" ? { target: value.target } : {}),
    ...(typeof value.proposalId === "number" && Number.isInteger(value.proposalId) ? { proposalId: value.proposalId } : {}),
    submittedAt: typeof value.submittedAt === "string" ? value.submittedAt : "",
    lifecycle: { ...lifecycle, state: lifecycleState as TransactionRecord["lifecycle"]["state"] },
    ...(typeof value.executionResult === "string" ? { executionResult: value.executionResult } : {}),
    childTransactionIds,
    verification: verification as TransactionRecord["verification"],
  };
}

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function listTransactions(): TransactionRecord[] {
  if (!canUseStorage()) return EMPTY_TRANSACTIONS as TransactionRecord[];
  const raw = readRaw();
  if (snapshotInitialized && raw === snapshotRaw) return snapshot as TransactionRecord[];
  snapshotInitialized = true;
  snapshotRaw = raw;
  if (!raw) {
    snapshot = EMPTY_TRANSACTIONS;
    return snapshot as TransactionRecord[];
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    const records = Array.isArray(parsed) ? parsed.map(normalizeRecord).filter((record): record is TransactionRecord => Boolean(record)) : [];
    snapshot = Object.freeze(records) as readonly TransactionRecord[];
  } catch {
    snapshot = EMPTY_TRANSACTIONS;
  }
  return snapshot as TransactionRecord[];
}

function readRaw(): string | null {
  try { return window.localStorage.getItem(STORAGE_KEY); } catch { return null; }
}

function notifyIfChanged(previousRaw: string | null): void {
  const nextRaw = readRaw();
  if (nextRaw === previousRaw) return;
  listTransactions();
  listeners.forEach((listener) => listener());
}

function dispatchTransactionEvent(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(TRANSACTION_EVENT));
}

export function subscribeTransactions(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) {
      const before = snapshotInitialized ? snapshotRaw : null;
      notifyIfChanged(before);
    }
  };
  const onLocalChange = () => {
    const before = snapshotInitialized ? snapshotRaw : null;
    notifyIfChanged(before);
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(TRANSACTION_EVENT, onLocalChange);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(TRANSACTION_EVENT, onLocalChange);
  };
}

export function getServerTransactionSnapshot(): readonly TransactionRecord[] { return EMPTY_TRANSACTIONS; }

export function createTransactionSnapshot(proposalId?: number): () => readonly TransactionRecord[] {
  let previousBase: readonly TransactionRecord[] | undefined;
  let previousResult: readonly TransactionRecord[] = EMPTY_TRANSACTIONS;
  return () => {
    const base = listTransactions();
    if (base === previousBase) return previousResult;
    previousBase = base;
    previousResult = proposalId === undefined ? base : Object.freeze(base.filter((record) => record.proposalId === proposalId));
    return previousResult;
  };
}

export function saveTransaction(record: TransactionRecord): void {
  if (!canUseStorage()) return;
  const previousRaw = readRaw();
  const current = listTransactions().filter((item) => item.hash !== record.hash);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify([record, ...current].slice(0, 100)));
  notifyIfChanged(previousRaw);
  dispatchTransactionEvent();
}

export function updateTransaction(hash: string, patch: Partial<TransactionRecord>): TransactionRecord | undefined {
  const current = listTransactions();
  const index = current.findIndex((item) => item.hash === hash.toLowerCase());
  if (index < 0) return undefined;
  const updated = { ...current[index], ...patch };
  if (canUseStorage()) {
    const previousRaw = readRaw();
    const next = [...current];
    next[index] = updated;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    notifyIfChanged(previousRaw);
    dispatchTransactionEvent();
  }
  return updated;
}

export function clearTransactions(): void {
  if (!canUseStorage()) return;
  const previousRaw = readRaw();
  window.localStorage.removeItem(STORAGE_KEY);
  notifyIfChanged(previousRaw);
  dispatchTransactionEvent();
}
