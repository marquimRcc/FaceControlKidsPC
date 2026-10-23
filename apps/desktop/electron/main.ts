import { app, BrowserWindow, ipcMain, shell } from "electron";
import { fileURLToPath } from "node:url";
import path from "node:path";
import net from "node:net";

const here = path.dirname(fileURLToPath(import.meta.url));
const role = process.argv.includes("--role=child") ? "child" : "admin";
const adminSocket = process.env.FACEKIDS_ADMIN_SOCKET ?? "/run/facekids/admin.sock";

function adminRequest(request: Record<string, unknown>): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const client = net.createConnection(adminSocket);
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

function createWindow() {
  const window = new BrowserWindow({
    width: role === "child" ? 680 : 1360,
    height: role === "child" ? 720 : 860,
    minWidth: role === "child" ? 520 : 1080,
    minHeight: role === "child" ? 600 : 700,
    backgroundColor: "#0b1020",
    title: role === "child" ? "FaceKids — Meu tempo" : "FaceKids — Painel dos pais",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(here, "preload.js"),
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

app.whenReady().then(() => {
  ipcMain.handle("facekids:get-context", () => ({
    role,
    platform: process.platform,
    backendConnected: false,
  }));
  ipcMain.handle("facekids:admin-state", async () => {
    const response = await adminRequest({ op: "status" });
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
  createWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

function typeOfNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
