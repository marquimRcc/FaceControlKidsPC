import { describe, expect, it } from "vitest";
import { demoSnapshot, disconnectedSnapshot, enrollmentStatusSchema, profilePhotoSchema, systemSnapshotSchema } from ".";

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

  it("accepts a child snapshot while no face is recognized", () => {
    const waiting = structuredClone(demoSnapshot);
    waiting.children = [];
    expect(systemSnapshotSchema.parse(waiting).children).toHaveLength(0);
    expect(disconnectedSnapshot.service).toBe("offline");
  });

  it("accepts enrollment status with camera preview and feedback", () => {
    const status = enrollmentStatusSchema.parse({
      childId: 1,
      samples: 3,
      requiredSamples: 12,
      state: "capturing",
      error: null,
      preview: "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
      feedback: "ok",
    });
    expect(status.preview).toBeDefined();
    expect(status.feedback).toBe("ok");
  });
});
