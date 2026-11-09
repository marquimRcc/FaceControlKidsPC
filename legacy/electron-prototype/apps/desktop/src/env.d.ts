import type { FaceKidsDesktopApi } from "@facekids/contracts";

declare global {
  interface Window {
    facekids?: FaceKidsDesktopApi;
  }
}

export {};
