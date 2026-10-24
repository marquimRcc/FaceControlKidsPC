import { z } from "zod";

export const childNameSchema = z.string().trim().min(1).max(80).refine(
  val => !/[\x00-\x1f\x7f]/.test(val),
  "Nome não pode conter caracteres de controle"
);

export const dailyLimitMinutesSchema = z.number().int().min(1).max(1440);
export const bonusMinutesSchema = z.number().int().min(1).max(480);

export const childStatusSchema = z.object({
  id: z.number().int().positive(),
  name: childNameSchema,
  initials: z.string().trim().min(1).max(3),
  remainingSeconds: z.number().int().nonnegative(),
  dailyLimitSeconds: z.number().int().positive(),
  bonusSeconds: z.number().int().nonnegative(),
  enrollmentSamples: z.number().int().nonnegative(),
  isPresent: z.boolean(),
  avatarPhoto: z.string().startsWith("data:image/jpeg;base64,").max(140_000).nullable().optional(),
  usageHistory: z.array(z.object({
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    usedSeconds: z.number().int().nonnegative(),
  })).max(31).default([]),
});

export const systemSnapshotSchema = z.object({
  generatedAt: z.string().datetime(),
  service: z.enum(["online", "offline", "attention"]),
  camera: z.enum(["ready", "busy", "offline"]),
  session: z.enum(["active", "locked", "absent"]),
  curfew: z.object({ enabled: z.boolean(), start: z.string(), end: z.string() }),
  children: z.array(childStatusSchema).max(20),
});

export type ChildStatus = z.infer<typeof childStatusSchema>;
export type SystemSnapshot = z.infer<typeof systemSnapshotSchema>;
export type DesktopRole = "admin" | "child";

export interface DesktopContext {
  role: DesktopRole;
  platform: "linux" | "win32" | "darwin";
  backendConnected: boolean;
}

export const enrollmentStatusSchema = z.object({
  childId: z.number().int().positive(),
  samples: z.number().int().nonnegative(),
  requiredSamples: z.number().int().positive(),
  state: z.enum(["capturing", "complete", "error"]),
  error: z.string().nullable(),
  preview: z.string().startsWith("data:image/jpeg;base64,").nullable().optional(),
  feedback: z.enum(["waiting", "ok", "multiple", "low_quality"]).nullable().optional(),
});

export const adminStateSchema = z.object({
  snapshot: systemSnapshotSchema,
  enrollment: enrollmentStatusSchema.nullable(),
});

export type EnrollmentStatus = z.infer<typeof enrollmentStatusSchema>;
export type AdminState = z.infer<typeof adminStateSchema>;
export const profilePhotoSchema = z.object({
  id: z.number().int().positive(),
  dataUrl: z.string().startsWith("data:image/jpeg;base64,").max(140_000),
  selected: z.boolean(),
});
export type ProfilePhoto = z.infer<typeof profilePhotoSchema>;
export const cameraProbeSchema = z.object({
  opened: z.boolean(),
  frames: z.number().int().nonnegative(),
  usable_frames: z.number().int().nonnegative(),
  faces_seen: z.number().int().nonnegative(),
  elapsed_seconds: z.number().nonnegative(),
  mean_brightness: z.number().nonnegative().nullable(),
});
export type CameraProbe = z.infer<typeof cameraProbeSchema>;

export interface FaceKidsDesktopApi {
  getContext(): Promise<DesktopContext>;
  getAdminState(): Promise<AdminState>;
  enrollChild(input: { name: string; minutes: number }): Promise<{ childId: number }>;
  cancelEnrollment(): Promise<void>;
  startEnrollment(childId: number): Promise<void>;
  listPhotos(childId: number): Promise<ProfilePhoto[]>;
  selectPhoto(childId: number, photoId: number): Promise<void>;
  renameChild(childId: number, name: string): Promise<void>;
  deleteChild(childId: number): Promise<void>;
  probeCamera(): Promise<CameraProbe>;
  setDailyLimit(childId: number, minutes: number): Promise<void>;
  addBonus(childId: number, minutes: number): Promise<void>;
  setCurfew(input: { enabled: boolean; start: string; end: string }): Promise<void>;
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
      isPresent: true,
      usageHistory: [
        { date: "2026-10-21", usedSeconds: 4200 },
        { date: "2026-10-22", usedSeconds: 5100 },
        { date: "2026-10-23", usedSeconds: 2160 }
      ]
    },
    {
      id: 2,
      name: "Lia",
      initials: "LI",
      remainingSeconds: 2100,
      dailyLimitSeconds: 5400,
      bonusSeconds: 0,
      enrollmentSamples: 12,
      isPresent: false,
      usageHistory: [
        { date: "2026-10-21", usedSeconds: 2700 },
        { date: "2026-10-22", usedSeconds: 3600 },
        { date: "2026-10-23", usedSeconds: 3300 }
      ]
    }
  ]
});

export const disconnectedSnapshot: SystemSnapshot = systemSnapshotSchema.parse({
  generatedAt: "2026-01-01T00:00:00.000Z",
  service: "offline",
  camera: "offline",
  session: "absent",
  curfew: { enabled: false, start: "08:00", end: "20:00" },
  children: [],
});
