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
});
