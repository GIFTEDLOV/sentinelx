import type { TransactionRecord } from "./types";

const STORAGE_KEY = "sentinelx.transaction-center.v1";

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function listTransactions(): TransactionRecord[] {
  if (!canUseStorage()) return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed as TransactionRecord[] : [];
  } catch { return []; }
}

export function saveTransaction(record: TransactionRecord): void {
  if (!canUseStorage()) return;
  const current = listTransactions().filter((item) => item.hash !== record.hash && item.operation !== record.operation);
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify([record, ...current].slice(0, 100)));
  window.dispatchEvent(new CustomEvent("sentinelx:transactions"));
}

export function updateTransaction(operation: string, patch: Partial<TransactionRecord>): TransactionRecord | undefined {
  const current = listTransactions();
  const index = current.findIndex((item) => item.operation === operation);
  if (index < 0) return undefined;
  const updated = { ...current[index], ...patch };
  current[index] = updated;
  if (canUseStorage()) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
    window.dispatchEvent(new CustomEvent("sentinelx:transactions"));
  }
  return updated;
}

export function clearTransactions(): void {
  if (canUseStorage()) window.localStorage.removeItem(STORAGE_KEY);
}
