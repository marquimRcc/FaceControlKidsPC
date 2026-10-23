import { describe, expect, it } from "vitest";
import { demoSnapshot, profilePhotoSchema, systemSnapshotSchema } from ".";

describe("systemSnapshotSchema", () => {
  it("accepts the typed demo state", () => {
    expect(systemSnapshotSchema.parse(demoSnapshot).children).toHaveLength(2);
  });

  it("rejects negative remaining time", () => {
    const invalid = structuredClone(demoSnapshot);
    invalid.children[0]!.remainingSeconds = -1;
    expect(() => systemSnapshotSchema.parse(invalid)).toThrow();
  });

  it("accepts only local JPEG profile photo payloads", () => {
    expect(profilePhotoSchema.parse({
      id: 1, dataUrl: "data:image/jpeg;base64,/9j/", selected: true,
    }).selected).toBe(true);
    expect(() => profilePhotoSchema.parse({
      id: 1, dataUrl: "https://example.com/child.jpg", selected: false,
    })).toThrow();
  });
});
