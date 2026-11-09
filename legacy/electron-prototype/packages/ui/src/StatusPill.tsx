import type { ReactNode } from "react";

export function StatusPill({ tone, children }: { tone: "ok" | "warn" | "muted"; children: ReactNode }) {
  return <span className={`status-pill status-pill--${tone}`}><i />{children}</span>;
}
