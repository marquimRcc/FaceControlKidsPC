import { contextBridge, ipcRenderer } from "electron";
import type { DesktopContext } from "@safepckids/contracts";

contextBridge.exposeInMainWorld("safepckids", {
  getContext: (): Promise<DesktopContext> => ipcRenderer.invoke("safepckids:get-context"),
  getAdminState: () => ipcRenderer.invoke("safepckids:admin-state"),
  enrollChild: (input: { name: string; minutes: number }) =>
    ipcRenderer.invoke("safepckids:enroll-child", input),
  cancelEnrollment: () => ipcRenderer.invoke("safepckids:cancel-enrollment"),
  startEnrollment: (childId: number) => ipcRenderer.invoke("safepckids:start-enrollment", childId),
  listPhotos: (childId: number) => ipcRenderer.invoke("safepckids:list-photos", childId),
  selectPhoto: (childId: number, photoId: number) =>
    ipcRenderer.invoke("safepckids:select-photo", childId, photoId),
  renameChild: (childId: number, name: string) =>
    ipcRenderer.invoke("safepckids:rename-child", childId, name),
  deleteChild: (childId: number) => ipcRenderer.invoke("safepckids:delete-child", childId),
  probeCamera: () => ipcRenderer.invoke("safepckids:probe-camera"),
  setDailyLimit: (childId: number, minutes: number) =>
    ipcRenderer.invoke("safepckids:set-daily-limit", childId, minutes),
  addBonus: (childId: number, minutes: number) =>
    ipcRenderer.invoke("safepckids:add-bonus", childId, minutes),
  setCurfew: (input: { enabled: boolean; start: string; end: string }) =>
    ipcRenderer.invoke("safepckids:set-curfew", input),
});
