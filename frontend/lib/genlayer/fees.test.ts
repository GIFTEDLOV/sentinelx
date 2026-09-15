import { describe, expect, it } from "vitest";
import type { TransactionFeeEstimate } from "genlayer-js/types";
import { feeEstimateToOptions, isGaslessFeeEstimate, profileEntryToOptions, validateFeeProfile } from "./fees";

const entry = { leaderTimeunitsAllocation: "125", validatorTimeunitsAllocation: "250", executionBudgetPerRound: "1000", totalMessageFees: "7", rotationsPerRound: "3" };
const policy = { enabled: true, genPerTimeUnit: BigInt(1), storageUnitPrice: BigInt(2), receiptGasPrice: BigInt(3), executionBudgetFloor: BigInt(4), timeUnitOverlayBps: 5 };

describe("V2 fee adapter", () => {
  it("accepts an explicitly versioned Studio-dev profile shape", () => {
    expect(validateFeeProfile({ version: 1, network: "studio_devnet", chainId: 61997, measuredAt: "now", deploy: entry, methods: { capture_evidence: entry } }).methods.capture_evidence).toEqual(entry);
  });

  it("rejects a profile from another chain", () => {
    expect(() => validateFeeProfile({ version: 1, network: "studio_devnet", chainId: 61127, methods: {} })).toThrow("chain 61997");
  });

  it("converts measured entries without inventing quantities", () => {
    expect(profileEntryToOptions(entry, 1)).toEqual({ leaderTimeunitsAllocation: 125, validatorTimeunitsAllocation: 250, appealRounds: 1, executionBudgetPerRound: 1000, totalMessageFees: 7, rotations: [3, 3] });
  });

  it("detects gasless from a disabled live policy", () => {
    expect(isGaslessFeeEstimate({ policy: { ...policy, enabled: false }, feeValue: BigInt(99) } as unknown as TransactionFeeEstimate)).toBe(true);
  });

  it("detects gasless from a zero live quote", () => {
    expect(isGaslessFeeEstimate({ policy, feeValue: BigInt(0) } as unknown as TransactionFeeEstimate)).toBe(true);
    expect(isGaslessFeeEstimate({ policy, feeValue: BigInt(1) } as unknown as TransactionFeeEstimate)).toBe(false);
  });

  it("carries the complete estimator fee fields into signing options", () => {
    const distribution = { leaderTimeunitsAllocation: 1, validatorTimeunitsAllocation: 2 };
    expect(feeEstimateToOptions({ policy, distribution, feeValue: BigInt(42), messageAllocations: [3] } as unknown as TransactionFeeEstimate)).toEqual({ distribution, messageAllocations: [3], feeValue: BigInt(42) });
  });
});
