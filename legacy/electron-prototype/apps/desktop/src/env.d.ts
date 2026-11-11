import type { SafePCKidsDesktopApi } from "@safepckids/contracts";

declare global {
  interface Window {
    safepckids?: SafePCKidsDesktopApi;
  }
}

export {};
