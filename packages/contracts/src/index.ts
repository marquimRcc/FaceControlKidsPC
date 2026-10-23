import { z } from "zod";

export const childStatusSchema = z.object({
  id: z.number().int().positive(),
  name: z.string().trim().min(1).max(80),
  initials: z.string().trim().min(1).max(3),
  remainingSeconds: z.number().int().nonnegative(),
  dailyLimitSeconds: z.number().int().positive(),
  bonusSeconds: z.number().int().nonnegative(),
  enrollmentSamples: z.number().int().nonnegative(),
  isPresent: z.boolean(),
});

export const systemSnapshotSchema = z.object({
  generatedAt: z.string().datetime(),
  service: z.enum(["online", "offline", "attention"]),
  camera: z.enum(["ready", "busy", "offline"]),
  session: z.enum(["active", "locked", "absent"]),
  curfew: z.object({ enabled: z.boolean(), start: z.string(), end: z.string() }),
  children: z.array(childStatusSchema).min(1),
});

export type ChildStatus = z.infer<typeof childStatusSchema>;
export type SystemSnapshot = z.infer<typeof systemSnapshotSchema>;
export type DesktopRole = "admin" | "child";

export interface DesktopContext {
  role: DesktopRole;
  platform: "linux" | "win32" | "darwin";
  backendConnected: boolean;
}

export const demoSnapshot: SystemSnapshot = systemSnapshotSchema.parse({
  generatedAt: "2026-10-23T12:00:00.000Z",
  service: "online",
  camera: "ready",
  session: "active",
  curfew: { enabled: true, start: "08:00", end: "20:00" },
  children: [
    {
      id: 1,
      name: "Miguel",
      initials: "MI",
      remainingSeconds: 5040,
      dailyLimitSeconds: 7200,
      bonusSeconds: 1800,
      enrollmentSamples: 12,
      isPresent: true
    },
    {
      id: 2,
      name: "Lia",
      initials: "LI",
      remainingSeconds: 2100,
      dailyLimitSeconds: 5400,
      bonusSeconds: 0,
      enrollmentSamples: 12,
      isPresent: false
    }
  ]
});
