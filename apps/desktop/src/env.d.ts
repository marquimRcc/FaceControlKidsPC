import type { DesktopContext } from "@facekids/contracts";

declare global {
  interface Window {
    facekids?: { getContext(): Promise<DesktopContext> };
  }
}

export {};
