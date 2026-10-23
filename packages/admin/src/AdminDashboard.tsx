import { useState } from "react";
import type { ChildStatus, EnrollmentStatus, ProfilePhoto, SystemSnapshot } from "@facekids/contracts";
import { ChildStatusCard, StatusPill } from "@facekids/ui";
import {
  Activity, CalendarClock, Camera, ChevronRight, CircleHelp, Clock3,
  LayoutDashboard, Plus, Settings, ShieldCheck, Sparkles, Users
} from "lucide-react";
import { EnrollmentWizard } from "./EnrollmentWizard";
import { ProfilePhotoManager } from "./ProfilePhotoManager";
import { ScheduleEditor } from "./ScheduleEditor";

const nav = [
  [LayoutDashboard, "Visão geral"],
  [Users, "Crianças"],
  [CalendarClock, "Horários"],
  [Activity, "Histórico"],
  [ShieldCheck, "Diagnóstico"],
  [Settings, "Configurações"],
] as const;

export function AdminDashboard({ snapshot, enrollment, backendError, onEnrollChild, onCancelEnrollment, onStartEnrollment, onListPhotos, onSelectPhoto, onSetDailyLimit, onAddBonus, onSetCurfew }: {
  snapshot: SystemSnapshot;
  enrollment: EnrollmentStatus | null;
  backendError: string | null;
  onEnrollChild: (name: string, minutes: number) => Promise<number>;
  onCancelEnrollment: () => Promise<void>;
  onStartEnrollment: (childId: number) => Promise<void>;
  onListPhotos: (childId: number) => Promise<ProfilePhoto[]>;
  onSelectPhoto: (childId: number, photoId: number) => Promise<void>;
  onSetDailyLimit: (childId: number, minutes: number) => Promise<void>;
  onAddBonus: (childId: number, minutes: number) => Promise<void>;
  onSetCurfew: (input: { enabled: boolean; start: string; end: string }) => Promise<void>;
}) {
  const [wizardOpen, setWizardOpen] = useState(false);
  const [selected, setSelected] = useState<ChildStatus | null>(null);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const today = new Intl.DateTimeFormat("pt-BR", {
    weekday: "long", day: "2-digit", month: "long",
  }).format(new Date()).toUpperCase();

  return (
    <div className="admin-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand__mark"><Sparkles size={21} /></div><div><strong>FaceKids</strong><span>Painel dos pais</span></div></div>
        <nav>{nav.map(([Icon, label], index) => <button key={label} className={index === 0 ? "active" : ""}><Icon size={19} /><span>{label}</span>{index === 1 && <b>{snapshot.children.length}</b>}</button>)}</nav>
        <div className="sidebar__help"><CircleHelp size={20} /><div><strong>Precisa de ajuda?</strong><span>Veja o guia de configuração</span></div><ChevronRight size={18} /></div>
        <div className="parent-chip"><div className="parent-chip__avatar">R</div><div><strong>Responsável</strong><span>Administrador</span></div></div>
      </aside>

      <main className="admin-content">
        {backendError && <div className="backend-alert" role="alert"><strong>Serviço não conectado</strong><span>{backendError}</span></div>}
        <header className="page-header">
          <div><span className="eyebrow">{today}</span><h1>Painel dos pais</h1><p>Acompanhe o tempo e cuide dos perfis das crianças.</p></div>
          <button className="button button--primary" onClick={() => setWizardOpen(true)}><Plus size={18} /> Nova criança</button>
        </header>

        <section className="health-strip" aria-label="Estado do sistema">
          <div><span className="health-icon health-icon--green"><ShieldCheck /></span><div><strong>{snapshot.service === "online" ? "Proteção ativa" : "Proteção indisponível"}</strong><StatusPill tone={snapshot.service === "online" ? "ok" : "warn"}>{snapshot.service === "online" ? "Serviço online" : "Serviço offline"}</StatusPill></div></div>
          <div><span className="health-icon health-icon--blue"><Camera /></span><div><strong>{snapshot.camera === "ready" ? "Câmera pronta" : snapshot.camera === "busy" ? "Câmera em uso" : "Câmera indisponível"}</strong><span>Reconhecimento local</span></div></div>
          <div><span className="health-icon health-icon--purple"><Clock3 /></span><div><strong>{snapshot.curfew.enabled ? "Horário configurado" : "Horário livre"}</strong><span>{snapshot.curfew.enabled ? `${snapshot.curfew.start} – ${snapshot.curfew.end}` : "Controle desativado"}</span></div></div>
        </section>

        <section className="section-heading"><div><h2>Perfis das crianças</h2><p>{snapshot.children.length} perfis configurados neste computador</p></div><button className="text-button">Ver detalhes <ChevronRight size={16} /></button></section>
        <section className="children-grid">
          {snapshot.children.map(child => <ChildStatusCard key={child.id} child={child} onOpen={setSelected} />)}
          <button className="add-child-card" onClick={() => setWizardOpen(true)}><span><Plus /></span><strong>Adicionar criança</strong><small>Crie um perfil com limite e cadastro facial próprios</small></button>
        </section>

        <section className="bottom-grid">
          <article className="panel"><div className="panel__heading"><div><span className="panel-icon"><CalendarClock /></span><div><h3>Rotina de hoje</h3><p>Horário compartilhado da conta filhos</p></div></div><button className="text-button" onClick={() => setScheduleOpen(true)}>Editar</button></div><div className={`schedule${snapshot.curfew.enabled ? "" : " schedule--disabled"}`}><span>{snapshot.curfew.start}</span><div><i /><b>{snapshot.curfew.enabled ? "Uso permitido" : "Controle desativado"}</b></div><span>{snapshot.curfew.end}</span></div></article>
          <article className="panel"><div className="panel__heading"><div><span className="panel-icon panel-icon--violet"><Activity /></span><div><h3>Estado atual</h3><p>Dados lidos do serviço local</p></div></div></div><ul className="activity-list"><li><i className="dot dot--green" /><div><strong>{snapshot.children.length} {snapshot.children.length === 1 ? "perfil configurado" : "perfis configurados"}</strong><span>cadastros protegidos neste computador</span></div></li><li><i className="dot dot--blue" /><div><strong>Câmera {snapshot.camera === "ready" ? "pronta" : snapshot.camera === "busy" ? "em uso" : "indisponível"}</strong><span>sessão {snapshot.session === "active" ? "ativa" : snapshot.session === "locked" ? "bloqueada" : "ausente"}</span></div></li></ul></article>
        </section>
      </main>
      {wizardOpen && <EnrollmentWizard enrollment={enrollment} onEnroll={onEnrollChild} onCancelEnrollment={onCancelEnrollment} onClose={() => setWizardOpen(false)} />}
      {selected && <ProfilePhotoManager child={selected} enrollment={enrollment} loadPhotos={onListPhotos} selectPhoto={onSelectPhoto} startCapture={onStartEnrollment} cancelCapture={onCancelEnrollment} setDailyLimit={onSetDailyLimit} addBonus={onAddBonus} onClose={() => setSelected(null)} />}
      {scheduleOpen && <ScheduleEditor current={snapshot.curfew} onSave={onSetCurfew} onClose={() => setScheduleOpen(false)} />}
    </div>
  );
}
