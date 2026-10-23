import { describe, expect, it } from "vitest";
import { demoSnapshot, systemSnapshotSchema } from ".";

describe("systemSnapshotSchema", () => {
  it("accepts the typed demo state", () => {
    expect(systemSnapshotSchema.parse(demoSnapshot).children).toHaveLength(2);
  });

  it("rejects negative remaining time", () => {
    const invalid = structuredClone(demoSnapshot);
    invalid.children[0]!.remainingSeconds = -1;
    expect(() => systemSnapshotSchema.parse(invalid)).toThrow();
  });
});
