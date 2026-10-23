import { useEffect, useState } from "react";
import { AdminDashboard } from "@facekids/admin";
import { demoSnapshot, type DesktopRole } from "@facekids/contracts";
import { ChildWelcome } from "./ChildWelcome";

function roleFromUrl(): DesktopRole {
  return new URLSearchParams(window.location.search).get("role") === "child" ? "child" : "admin";
}

export function App() {
  const [role, setRole] = useState<DesktopRole>(roleFromUrl());
  useEffect(() => { void window.facekids?.getContext().then(context => setRole(context.role)); }, []);

  return <div className="app-root">
    {role === "child" ? <ChildWelcome snapshot={demoSnapshot} /> : <AdminDashboard snapshot={demoSnapshot} />}
    {!window.facekids && <div className="prototype-switch" aria-label="Alternar protótipo"><button className={role === "admin" ? "active" : ""} onClick={() => setRole("admin")}>Painel</button><button className={role === "child" ? "active" : ""} onClick={() => setRole("child")}>Criança</button></div>}
  </div>;
}
