import { contextBridge, ipcRenderer } from "electron";
import type { DesktopContext } from "@facekids/contracts";

contextBridge.exposeInMainWorld("facekids", {
  getContext: (): Promise<DesktopContext> => ipcRenderer.invoke("facekids:get-context"),
  getAdminState: () => ipcRenderer.invoke("facekids:admin-state"),
  enrollChild: (input: { name: string; minutes: number }) =>
    ipcRenderer.invoke("facekids:enroll-child", input),
  cancelEnrollment: () => ipcRenderer.invoke("facekids:cancel-enrollment"),
  startEnrollment: (childId: number) => ipcRenderer.invoke("facekids:start-enrollment", childId),
  listPhotos: (childId: number) => ipcRenderer.invoke("facekids:list-photos", childId),
  selectPhoto: (childId: number, photoId: number) =>
    ipcRenderer.invoke("facekids:select-photo", childId, photoId),
  renameChild: (childId: number, name: string) =>
    ipcRenderer.invoke("facekids:rename-child", childId, name),
  deleteChild: (childId: number) => ipcRenderer.invoke("facekids:delete-child", childId),
  setDailyLimit: (childId: number, minutes: number) =>
    ipcRenderer.invoke("facekids:set-daily-limit", childId, minutes),
  addBonus: (childId: number, minutes: number) =>
    ipcRenderer.invoke("facekids:add-bonus", childId, minutes),
  setCurfew: (input: { enabled: boolean; start: string; end: string }) =>
    ipcRenderer.invoke("facekids:set-curfew", input),
});
