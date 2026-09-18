import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearTransactions, createTransactionSnapshot, listTransactions, saveTransaction, subscribeTransactions, updateTransaction } from "./transactions";
import type { TransactionRecord } from "./types";

const HASH_A = `0x${"a".repeat(64)}`;
const HASH_B = `0x${"b".repeat(64)}`;
const record = (operation: string, hash: string): TransactionRecord => ({
  operation, hash, submittedAt: new Date(0).toISOString(), lifecycle: { state: "processing" }, childTransactionIds: [], verification: "pending",
});

describe("transaction external store", () => {
  beforeEach(() => {
    window.localStorage.clear();
    clearTransactions();
  });

  it("returns a referentially stable snapshot until storage changes", () => {
    expect(listTransactions()).toBe(listTransactions());
    saveTransaction(record("review", HASH_A));
    const first = listTransactions();
    expect(listTransactions()).toBe(first);
    saveTransaction(record("review", HASH_B));
    expect(listTransactions()).not.toBe(first);
  });

  it("keeps same-operation transactions distinct and updates by hash", () => {
    saveTransaction(record("review", HASH_A));
    saveTransaction(record("review", HASH_B));
    expect(listTransactions().map((item) => item.hash)).toEqual([HASH_B, HASH_A]);
    updateTransaction(HASH_A, { verification: "successful", lifecycle: { state: "finalized" } });
    expect(listTransactions().find((item) => item.hash === HASH_A)?.verification).toBe("successful");
    expect(listTransactions().find((item) => item.hash === HASH_B)?.verification).toBe("pending");
  });

  it("fails safely for corrupt, empty and legacy records", () => {
    window.localStorage.setItem("sentinelx.transaction-center.v1", "not-json");
    expect(listTransactions()).toEqual([]);
    window.localStorage.setItem("sentinelx.transaction-center.v1", JSON.stringify([{ operation: "old", hash: "bad" }]));
    expect(listTransactions()).toEqual([]);
    window.localStorage.removeItem("sentinelx.transaction-center.v1");
    expect(listTransactions()).toEqual([]);
  });

  it("notifies subscribers for a cross-tab storage update", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeTransactions(listener);
    window.localStorage.setItem("sentinelx.transaction-center.v1", JSON.stringify([record("review", HASH_A)]));
    window.dispatchEvent(new StorageEvent("storage", { key: "sentinelx.transaction-center.v1", newValue: window.localStorage.getItem("sentinelx.transaction-center.v1") }));
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("keeps a filtered proposal snapshot stable", () => {
    saveTransaction({ ...record("review", HASH_A), proposalId: 1 });
    const snapshot = createTransactionSnapshot(1);
    expect(snapshot()).toBe(snapshot());
    saveTransaction({ ...record("review", HASH_B), proposalId: 2 });
    expect(snapshot()).toHaveLength(1);
    expect(snapshot()[0].proposalId).toBe(1);
  });
});
