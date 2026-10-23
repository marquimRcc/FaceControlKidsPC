import { describe, expect, it } from "vitest";
import { cameraProbeSchema, demoSnapshot, disconnectedSnapshot, enrollmentStatusSchema, profilePhotoSchema, systemSnapshotSchema } from ".";

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

  it("validates non-biometric camera diagnostics", () => {
    const probe = cameraProbeSchema.parse({
      opened: true, frames: 50, usable_frames: 49, faces_seen: 2,
      elapsed_seconds: 5, mean_brightness: 112.5,
    });
    expect(probe.usable_frames).toBe(49);
    expect(() => cameraProbeSchema.parse({ ...probe, frames: -1 })).toThrow();
  });
});
