import { contextBridge, ipcRenderer } from "electron";
import type { DesktopContext } from "@facekids/contracts";

contextBridge.exposeInMainWorld("facekids", {
  getContext: (): Promise<DesktopContext> => ipcRenderer.invoke("facekids:get-context"),
});
