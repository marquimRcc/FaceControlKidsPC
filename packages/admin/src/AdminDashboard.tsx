import { useState } from "react";
import type { ChildStatus, EnrollmentStatus, SystemSnapshot } from "@facekids/contracts";
import { ChildStatusCard, StatusPill } from "@facekids/ui";
import {
  Activity, CalendarClock, Camera, ChevronRight, CircleHelp, Clock3,
  LayoutDashboard, Plus, Settings, ShieldCheck, Sparkles, Users
} from "lucide-react";
import { EnrollmentWizard } from "./EnrollmentWizard";

const nav = [
  [LayoutDashboard, "Visão geral"],
  [Users, "Crianças"],
  [CalendarClock, "Horários"],
  [Activity, "Histórico"],
  [ShieldCheck, "Diagnóstico"],
  [Settings, "Configurações"],
] as const;

export function AdminDashboard({ snapshot, enrollment, backendError, onEnrollChild, onCancelEnrollment }: {
  snapshot: SystemSnapshot;
  enrollment: EnrollmentStatus | null;
  backendError: string | null;
  onEnrollChild: (name: string, minutes: number) => Promise<number>;
  onCancelEnrollment: () => Promise<void>;
}) {
  const [wizardOpen, setWizardOpen] = useState(false);
  const [selected, setSelected] = useState<ChildStatus | null>(null);

  return (
    <div className="admin-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand__mark"><Sparkles size={21} /></div><div><strong>FaceKids</strong><span>Painel dos pais</span></div></div>
        <nav>{nav.map(([Icon, label], index) => <button key={label} className={index === 0 ? "active" : ""}><Icon size={19} /><span>{label}</span>{index === 1 && <b>{snapshot.children.length}</b>}</button>)}</nav>
        <div className="sidebar__help"><CircleHelp size={20} /><div><strong>Precisa de ajuda?</strong><span>Veja o guia de configuração</span></div><ChevronRight size={18} /></div>
        <div className="parent-chip"><div className="parent-chip__avatar">MQ</div><div><strong>Marcos</strong><span>Administrador</span></div></div>
      </aside>

      <main className="admin-content">
        {backendError && <div className="backend-alert" role="alert"><strong>Serviço não conectado</strong><span>{backendError}</span></div>}
        <header className="page-header">
          <div><span className="eyebrow">QUINTA-FEIRA, 23 DE OUTUBRO</span><h1>Bom dia, Marcos</h1><p>Acompanhe o tempo e cuide dos perfis das crianças.</p></div>
          <button className="button button--primary" onClick={() => setWizardOpen(true)}><Plus size={18} /> Nova criança</button>
        </header>

        <section className="health-strip" aria-label="Estado do sistema">
          <div><span className="health-icon health-icon--green"><ShieldCheck /></span><div><strong>Proteção ativa</strong><StatusPill tone="ok">Serviço online</StatusPill></div></div>
          <div><span className="health-icon health-icon--blue"><Camera /></span><div><strong>Câmera pronta</strong><span>USB 2.0 Camera</span></div></div>
          <div><span className="health-icon health-icon--purple"><Clock3 /></span><div><strong>Horário permitido</strong><span>{snapshot.curfew.start} – {snapshot.curfew.end}</span></div></div>
        </section>

        <section className="section-heading"><div><h2>Perfis das crianças</h2><p>{snapshot.children.length} perfis configurados neste computador</p></div><button className="text-button">Ver detalhes <ChevronRight size={16} /></button></section>
        <section className="children-grid">
          {snapshot.children.map(child => <ChildStatusCard key={child.id} child={child} onOpen={setSelected} />)}
          <button className="add-child-card" onClick={() => setWizardOpen(true)}><span><Plus /></span><strong>Adicionar criança</strong><small>Crie um perfil com limite e cadastro facial próprios</small></button>
        </section>

        <section className="bottom-grid">
          <article className="panel"><div className="panel__heading"><div><span className="panel-icon"><CalendarClock /></span><div><h3>Rotina de hoje</h3><p>Horário compartilhado da conta filhos</p></div></div><button className="text-button">Editar</button></div><div className="schedule"><span>08:00</span><div><i /><b>Uso permitido</b></div><span>20:00</span></div></article>
          <article className="panel"><div className="panel__heading"><div><span className="panel-icon panel-icon--violet"><Activity /></span><div><h3>Atividade recente</h3><p>Eventos processados localmente</p></div></div></div><ul className="activity-list"><li><i className="dot dot--green" /><div><strong>Miguel foi reconhecido</strong><span>há 4 minutos</span></div></li><li><i className="dot dot--blue" /><div><strong>Bônus de 30 min concedido</strong><span>hoje, 08:14</span></div></li></ul></article>
        </section>
      </main>
      {wizardOpen && <EnrollmentWizard enrollment={enrollment} onEnroll={onEnrollChild} onCancelEnrollment={onCancelEnrollment} onClose={() => setWizardOpen(false)} />}
      {selected && <div className="toast" role="status">Perfil de {selected.name} selecionado para a próxima etapa.<button onClick={() => setSelected(null)}>Fechar</button></div>}
    </div>
  );
}
