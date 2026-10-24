import { describe, expect, it } from "vitest";
import { bonusMinutesSchema, cameraProbeSchema, childNameSchema, dailyLimitMinutesSchema, demoSnapshot, disconnectedSnapshot, enrollmentStatusSchema, profilePhotoSchema, systemSnapshotSchema } from ".";

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

  it("validates child usage history records", () => {
    const valid = structuredClone(demoSnapshot);
    valid.children[0]!.usageHistory = [
      { date: "2026-10-23", usedSeconds: 3600 },
    ];
    expect(systemSnapshotSchema.parse(valid).children[0]!.usageHistory).toHaveLength(1);

    const invalidDate = structuredClone(demoSnapshot);
    invalidDate.children[0]!.usageHistory = [
      { date: "23-10-2026", usedSeconds: 3600 },
    ];
    expect(() => systemSnapshotSchema.parse(invalidDate)).toThrow();

    const negativeSeconds = structuredClone(demoSnapshot);
    negativeSeconds.children[0]!.usageHistory = [
      { date: "2026-10-23", usedSeconds: -10 },
    ];
    expect(() => systemSnapshotSchema.parse(negativeSeconds)).toThrow();
  });

  it("validates and sanitizes child names", () => {
    expect(childNameSchema.parse("  Lucas  ")).toBe("Lucas");
    expect(childNameSchema.parse("Maria Eduarda")).toBe("Maria Eduarda");
    expect(() => childNameSchema.parse("")).toThrow();
    expect(() => childNameSchema.parse("   ")).toThrow();
    expect(() => childNameSchema.parse("A".repeat(81))).toThrow();
    expect(() => childNameSchema.parse("Lucas\x00Injection")).toThrow();
    expect(() => childNameSchema.parse("Lucas\nNewline")).toThrow();
    expect(() => childNameSchema.parse("Lucas\x1b[31mRed")).toThrow();
  });

  it("validates daily limit and bonus ranges", () => {
    expect(dailyLimitMinutesSchema.parse(60)).toBe(60);
    expect(dailyLimitMinutesSchema.parse(1440)).toBe(1440);
    expect(() => dailyLimitMinutesSchema.parse(0)).toThrow();
    expect(() => dailyLimitMinutesSchema.parse(1441)).toThrow();
    expect(() => dailyLimitMinutesSchema.parse(60.5)).toThrow();

    expect(bonusMinutesSchema.parse(30)).toBe(30);
    expect(bonusMinutesSchema.parse(480)).toBe(480);
    expect(() => bonusMinutesSchema.parse(0)).toThrow();
    expect(() => bonusMinutesSchema.parse(481)).toThrow();
  });
});
