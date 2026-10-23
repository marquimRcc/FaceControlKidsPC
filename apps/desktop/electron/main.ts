import { app, BrowserWindow, ipcMain, shell } from "electron";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const role = process.argv.includes("--role=child") ? "child" : "admin";

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
  createWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
