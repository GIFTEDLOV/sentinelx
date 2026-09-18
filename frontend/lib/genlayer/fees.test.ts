import { describe, expect, it } from "vitest";
import { validateFeeProfile } from "./fees";

const entry = { gasUsed: "125000", transactionValue: "0" };

describe("Studionet stable fee adapter", () => {
  it("accepts the native stable gas profile shape", () => {
    expect(validateFeeProfile({ version: 1, network: "studionet", chainId: 61999, measuredAt: "now", deploy: entry, methods: { capture_evidence: entry } }).methods.capture_evidence).toEqual(entry);
  });

  it("rejects a profile from another chain", () => {
    expect(() => validateFeeProfile({ version: 1, network: "studionet", chainId: 61127, methods: {} })).toThrow("chain 61999");
  });

  it("rejects non-numeric native gas observations", () => {
    expect(() => validateFeeProfile({ version: 1, network: "studionet", chainId: 61999, methods: { capture_evidence: { ...entry, gasUsed: "guess" } } })).toThrow("invalid measured stable gas entry");
  });
});
