import { useCallback, useEffect, useRef, useState } from "react";
import { AdminDashboard } from "@facekids/admin";
import { adminStateSchema, demoSnapshot, disconnectedSnapshot, profilePhotoSchema, type AdminState, type DesktopRole } from "@facekids/contracts";
import { ChildWelcome } from "./ChildWelcome";

function roleFromUrl(): DesktopRole {
  return new URLSearchParams(window.location.search).get("role") === "child" ? "child" : "admin";
}

export function App() {
  const [role, setRole] = useState<DesktopRole>(roleFromUrl());
  const [adminState, setAdminState] = useState<AdminState>({
    snapshot: window.facekids ? disconnectedSnapshot : demoSnapshot,
    enrollment: null,
  });
  const [backendError, setBackendError] = useState<string | null>(null);
  const pollTimerRef = useRef<number | null>(null);

  useEffect(() => { void window.facekids?.getContext().then(context => setRole(context.role)); }, []);

  // Smooth local countdown every 1 second for present child without polling backend aggressively
  useEffect(() => {
    const timer = window.setInterval(() => {
      setAdminState(prev => {
        const hasPresent = prev.snapshot.children.some(c => c.isPresent && c.remainingSeconds > 0);
        if (!hasPresent) return prev;
        return {
          ...prev,
          snapshot: {
            ...prev.snapshot,
            children: prev.snapshot.children.map(child =>
              child.isPresent && child.remainingSeconds > 0
                ? { ...child, remainingSeconds: child.remainingSeconds - 1 }
                : child
            ),
          },
        };
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const refresh = useCallback(async (): Promise<boolean> => {
    if (!window.facekids) return false;
    try {
      const state = adminStateSchema.parse(await window.facekids.getAdminState());
      setAdminState(state);
      setBackendError(null);
      return state.enrollment?.state === "capturing";
    } catch (error) {
      setAdminState({ snapshot: disconnectedSnapshot, enrollment: null });
      setBackendError(error instanceof Error ? error.message : "Serviço indisponível");
      return false;
    }
  }, []);

  const scheduleNextPoll = useCallback((delayMs: number) => {
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
    }
    pollTimerRef.current = window.setTimeout(async () => {
      const isCapturing = await refresh();
      scheduleNextPoll(isCapturing ? 600 : 5000);
    }, delayMs);
  }, [refresh]);

  const triggerImmediateRefresh = useCallback(async () => {
    const isCapturing = await refresh();
    scheduleNextPoll(isCapturing ? 600 : 5000);
  }, [refresh, scheduleNextPoll]);

  useEffect(() => {
    if (!window.facekids) return;
    void triggerImmediateRefresh();
    return () => {
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [role, triggerImmediateRefresh]);

  const enrollChild = async (name: string, minutes: number) => {
    if (!window.facekids) throw new Error("Cadastro real disponível somente no aplicativo desktop");
    const result = await window.facekids.enrollChild({ name, minutes });
    void triggerImmediateRefresh();
    return result.childId;
  };

  return <div className="app-root">
    {role === "child" ? <ChildWelcome snapshot={adminState.snapshot} /> : <AdminDashboard snapshot={adminState.snapshot} enrollment={adminState.enrollment} backendError={backendError} onEnrollChild={enrollChild} onCancelEnrollment={async () => { await window.facekids?.cancelEnrollment(); void triggerImmediateRefresh(); }} onStartEnrollment={async childId => { if (!window.facekids) throw new Error("Disponível somente no aplicativo"); await window.facekids.startEnrollment(childId); void triggerImmediateRefresh(); }} onListPhotos={async childId => profilePhotoSchema.array().parse(await window.facekids?.listPhotos(childId))} onSelectPhoto={async (childId, photoId) => { if (!window.facekids) throw new Error("Disponível somente no aplicativo"); await window.facekids.selectPhoto(childId, photoId); void triggerImmediateRefresh(); }} onSetDailyLimit={async (childId, minutes) => { if (!window.facekids) throw new Error("Disponível somente no aplicativo"); await window.facekids.setDailyLimit(childId, minutes); void triggerImmediateRefresh(); }} onAddBonus={async (childId, minutes) => { if (!window.facekids) throw new Error("Disponível somente no aplicativo"); await window.facekids.addBonus(childId, minutes); void triggerImmediateRefresh(); }} onSetCurfew={async input => { if (!window.facekids) throw new Error("Disponível somente no aplicativo"); await window.facekids.setCurfew(input); void triggerImmediateRefresh(); }} />}
    {!window.facekids && <div className="prototype-switch" aria-label="Alternar protótipo"><button className={role === "admin" ? "active" : ""} onClick={() => setRole("admin")}>Painel</button><button className={role === "child" ? "active" : ""} onClick={() => setRole("child")}>Criança</button></div>}
  </div>;
}
