import { useEffect, useState } from "react";
import { AdminDashboard } from "@facekids/admin";
import { adminStateSchema, demoSnapshot, profilePhotoSchema, type AdminState, type DesktopRole } from "@facekids/contracts";
import { ChildWelcome } from "./ChildWelcome";

function roleFromUrl(): DesktopRole {
  return new URLSearchParams(window.location.search).get("role") === "child" ? "child" : "admin";
}

export function App() {
  const [role, setRole] = useState<DesktopRole>(roleFromUrl());
  const [adminState, setAdminState] = useState<AdminState>({ snapshot: demoSnapshot, enrollment: null });
  const [backendError, setBackendError] = useState<string | null>(null);
  useEffect(() => { void window.facekids?.getContext().then(context => setRole(context.role)); }, []);
  useEffect(() => {
    if (!window.facekids || role !== "admin") return;
    let active = true;
    const refresh = async () => {
      try {
        const state = adminStateSchema.parse(await window.facekids!.getAdminState());
        if (active) { setAdminState(state); setBackendError(null); }
      } catch (error) {
        if (active) setBackendError(error instanceof Error ? error.message : "Serviço indisponível");
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [role]);

  const enrollChild = async (name: string, minutes: number) => {
    if (!window.facekids) throw new Error("Cadastro real disponível somente no aplicativo desktop");
    const result = await window.facekids.enrollChild({ name, minutes });
    return result.childId;
  };

  return <div className="app-root">
    {role === "child" ? <ChildWelcome snapshot={adminState.snapshot} /> : <AdminDashboard snapshot={adminState.snapshot} enrollment={adminState.enrollment} backendError={backendError} onEnrollChild={enrollChild} onCancelEnrollment={async () => { await window.facekids?.cancelEnrollment(); }} onStartEnrollment={async childId => { if (!window.facekids) throw new Error("Disponível somente no aplicativo"); await window.facekids.startEnrollment(childId); }} onListPhotos={async childId => profilePhotoSchema.array().parse(await window.facekids?.listPhotos(childId))} onSelectPhoto={async (childId, photoId) => { if (!window.facekids) throw new Error("Disponível somente no aplicativo"); await window.facekids.selectPhoto(childId, photoId); }} />}
    {!window.facekids && <div className="prototype-switch" aria-label="Alternar protótipo"><button className={role === "admin" ? "active" : ""} onClick={() => setRole("admin")}>Painel</button><button className={role === "child" ? "active" : ""} onClick={() => setRole("child")}>Criança</button></div>}
  </div>;
}
