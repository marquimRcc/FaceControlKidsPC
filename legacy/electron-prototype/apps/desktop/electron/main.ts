import { app, BrowserWindow, ipcMain, shell } from "electron";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";
import path from "node:path";
import net from "node:net";

const here = path.dirname(fileURLToPath(import.meta.url));
const role = process.argv.includes("--role=child") ? "child" : "admin";
const packagedIcon = path.join(here, "../assets/facekids-256.png");
const workspaceIcon = path.join(here, "../../../assets/facekids-256.png");
const appIcon = existsSync(packagedIcon) ? packagedIcon : workspaceIcon;
const adminSocket = process.env.FACEKIDS_ADMIN_SOCKET ?? "/run/facekids/admin.sock";
const childSocket = process.env.FACEKIDS_CHILD_SOCKET ?? "/run/facekids-child/status.sock";

function socketRequest(socketPath: string, request: Record<string, unknown>): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const client = net.createConnection(socketPath);
    let response = "";
    const fail = (error: Error) => { client.destroy(); reject(error); };
    client.setTimeout(4000, () => fail(new Error("O serviço FaceKids não respondeu")));
    client.on("connect", () => client.write(`${JSON.stringify(request)}\n`));
    client.on("data", chunk => {
      response += chunk.toString("utf8");
      if (response.length > 3_000_000) fail(new Error("Resposta do serviço excedeu o limite"));
      if (!response.includes("\n")) return;
      client.end();
      try {
        const parsed = JSON.parse(response.split("\n", 1)[0]!) as Record<string, unknown>;
        if (parsed.ok !== true) reject(new Error(String(parsed.error ?? "Operação recusada")));
        else resolve(parsed);
      } catch (error) { reject(error); }
    });
    client.on("error", reject);
  });
}

const adminRequest = (request: Record<string, unknown>) => {
  if (role !== "admin") {
    return Promise.reject(new Error("Operação disponível somente no painel responsável"));
  }
  return socketRequest(adminSocket, request);
};

function createWindow() {
  const window = new BrowserWindow({
    width: role === "child" ? 680 : 1360,
    height: role === "child" ? 720 : 860,
    minWidth: role === "child" ? 520 : 1080,
    minHeight: role === "child" ? 600 : 700,
    backgroundColor: "#0b1020",
    icon: appIcon,
    title: role === "child" ? "FaceKids — Meu tempo" : "FaceKids — Painel dos pais",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(here, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://docs.facekids.local/")) void shell.openExternal(url);
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", event => event.preventDefault());

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) void window.loadURL(`${devUrl}?role=${role}`);
  else void window.loadFile(path.join(here, "../dist/index.html"), { query: { role } });
}

app.setName("FaceKids");

app.whenReady().then(() => {
  ipcMain.handle("facekids:get-context", () => ({
    role,
    platform: process.platform,
    backendConnected: false,
  }));
  ipcMain.handle("facekids:admin-state", async () => {
    const response = await socketRequest(
      role === "child" ? childSocket : adminSocket, { op: "status" },
    );
    return { snapshot: response.snapshot, enrollment: response.enrollment ?? null };
  });
  ipcMain.handle("facekids:enroll-child", async (_event, input: unknown) => {
    if (!input || typeof input !== "object") throw new Error("Cadastro inválido");
    const { name, minutes } = input as { name?: unknown; minutes?: unknown };
    if (typeof name !== "string" || !name.trim() || name.trim().length > 80 ||
        typeOfNumber(minutes) === false || minutes < 1 || minutes > 1440) {
      throw new Error("Nome ou limite inválido");
    }
    const added = await adminRequest({
      op: "add_child_and_start_enrollment", name: name.trim(), minutes,
    });
    return { childId: added.childId };
  });
  ipcMain.handle("facekids:cancel-enrollment", async () => {
    await adminRequest({ op: "cancel_enrollment" });
  });
  ipcMain.handle("facekids:start-enrollment", async (_event, childId: unknown) => {
    if (!typeOfNumber(childId) || childId <= 0) throw new Error("Criança inválida");
    await adminRequest({ op: "start_enrollment", childId });
  });
  ipcMain.handle("facekids:list-photos", async (_event, childId: unknown) => {
    if (!typeOfNumber(childId) || childId <= 0) throw new Error("Criança inválida");
    const response = await adminRequest({ op: "list_photos", childId });
    return response.photos;
  });
  ipcMain.handle("facekids:select-photo", async (
    _event, childId: unknown, photoId: unknown,
  ) => {
    if (!typeOfNumber(childId) || childId <= 0 ||
        !typeOfNumber(photoId) || photoId <= 0) throw new Error("Foto inválida");
    await adminRequest({ op: "select_photo", childId, photoId });
  });
  ipcMain.handle("facekids:rename-child", async (
    _event, childId: unknown, name: unknown,
  ) => {
    if (!typeOfNumber(childId) || childId <= 0 || typeof name !== "string" ||
        !name.trim() || name.trim().length > 80) {
      throw new Error("Criança ou nome inválido");
    }
    await adminRequest({ op: "rename_child", childId, name: name.trim() });
  });
  ipcMain.handle("facekids:delete-child", async (_event, childId: unknown) => {
    if (!typeOfNumber(childId) || childId <= 0) throw new Error("Criança inválida");
    await adminRequest({ op: "delete_child", childId });
  });
  ipcMain.handle("facekids:probe-camera", async () => {
    const response = await adminRequest({ op: "probe", seconds: 5 });
    return response.probe;
  });
  ipcMain.handle("facekids:set-daily-limit", async (
    _event, childId: unknown, minutes: unknown,
  ) => {
    if (!typeOfNumber(childId) || childId <= 0 ||
        !typeOfNumber(minutes) || minutes < 1 || minutes > 1440) {
      throw new Error("Criança ou limite diário inválido");
    }
    await adminRequest({ op: "set_daily_limit", childId, minutes });
  });
  ipcMain.handle("facekids:add-bonus", async (
    _event, childId: unknown, minutes: unknown,
  ) => {
    if (!typeOfNumber(childId) || childId <= 0 ||
        !typeOfNumber(minutes) || minutes < 1 || minutes > 480) {
      throw new Error("Criança ou bônus inválido");
    }
    await adminRequest({ op: "add_bonus", childId, minutes });
  });
  ipcMain.handle("facekids:set-curfew", async (_event, input: unknown) => {
    if (!input || typeof input !== "object") throw new Error("Horário inválido");
    const { enabled, start, end } = input as Record<string, unknown>;
    const clock = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
    if (typeof enabled !== "boolean" || typeof start !== "string" ||
        typeof end !== "string" || !clock.test(start) || !clock.test(end)) {
      throw new Error("Horário inválido");
    }
    await adminRequest({ op: "set_curfew", enabled, start, end });
  });
  createWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

function typeOfNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
