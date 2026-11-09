import { useState, type ReactNode } from "react";
import type { CameraProbe, ChildStatus, EnrollmentStatus, ProfilePhoto, SystemSnapshot } from "@facekids/contracts";
import { ChildStatusCard, formatTime, StatusPill } from "@facekids/ui";
import { Activity, CalendarClock, Camera, ChevronRight, CircleHelp, Clock3, Database, LayoutDashboard, LockKeyhole, Plus, RefreshCw, Settings, ShieldCheck, Sparkles, Users } from "lucide-react";
import { EnrollmentWizard } from "./EnrollmentWizard";
import { ProfilePhotoManager } from "./ProfilePhotoManager";
import { ScheduleEditor } from "./ScheduleEditor";

type Section = "overview" | "children" | "schedule" | "history" | "diagnostics" | "settings";
const nav: ReadonlyArray<readonly [Section, typeof LayoutDashboard, string]> = [
  ["overview", LayoutDashboard, "Visão geral"], ["children", Users, "Crianças"],
  ["schedule", CalendarClock, "Horários"], ["history", Activity, "Histórico"],
  ["diagnostics", ShieldCheck, "Diagnóstico"], ["settings", Settings, "Configurações"],
];
const titles: Record<Section, readonly [string, string]> = {
  overview: ["Painel dos pais", "Acompanhe o tempo e cuide dos perfis das crianças."],
  children: ["Crianças", "Gerencie perfis, fotos e limites diários."],
  schedule: ["Horários", "Defina quando a conta filhos pode ser usada."],
  history: ["Histórico de uso", "Consulte o tempo usado nos últimos sete dias."],
  diagnostics: ["Diagnóstico", "Confira a conexão e os recursos de proteção."],
  settings: ["Configurações", "Veja as regras ativas neste computador."],
};

function StatePanel({ snapshot }: { snapshot: SystemSnapshot }) {
  return <section className="health-strip" aria-label="Estado do sistema">
    <div><span className="health-icon health-icon--green"><ShieldCheck /></span><div><strong>{snapshot.service === "online" ? "Proteção ativa" : "Proteção indisponível"}</strong><StatusPill tone={snapshot.service === "online" ? "ok" : "warn"}>{snapshot.service === "online" ? "Serviço online" : "Serviço offline"}</StatusPill></div></div>
    <div><span className="health-icon health-icon--blue"><Camera /></span><div><strong>{snapshot.camera === "ready" ? "Câmera pronta" : snapshot.camera === "busy" ? "Câmera em uso" : "Câmera indisponível"}</strong><span>Reconhecimento local</span></div></div>
    <div><span className="health-icon health-icon--purple"><Clock3 /></span><div><strong>{snapshot.curfew.enabled ? "Horário configurado" : "Horário livre"}</strong><span>{snapshot.curfew.enabled ? `${snapshot.curfew.start} – ${snapshot.curfew.end}` : "Controle desativado"}</span></div></div>
  </section>;
}

export function AdminDashboard({ snapshot, enrollment, backendError, onEnrollChild, onCancelEnrollment, onStartEnrollment, onListPhotos, onSelectPhoto, onRenameChild, onDeleteChild, onProbeCamera, onSetDailyLimit, onAddBonus, onSetCurfew }: {
  snapshot: SystemSnapshot; enrollment: EnrollmentStatus | null; backendError: string | null;
  onEnrollChild: (name: string, minutes: number) => Promise<number>; onCancelEnrollment: () => Promise<void>;
  onStartEnrollment: (childId: number) => Promise<void>; onListPhotos: (childId: number) => Promise<ProfilePhoto[]>;
  onSelectPhoto: (childId: number, photoId: number) => Promise<void>; onRenameChild: (childId: number, name: string) => Promise<void>;
  onDeleteChild: (childId: number) => Promise<void>;
  onProbeCamera: () => Promise<CameraProbe>;
  onSetDailyLimit: (childId: number, minutes: number) => Promise<void>;
  onAddBonus: (childId: number, minutes: number) => Promise<void>; onSetCurfew: (input: { enabled: boolean; start: string; end: string }) => Promise<void>;
}) {
  const [activeSection, setActiveSection] = useState<Section>("overview");
  const [wizardOpen, setWizardOpen] = useState(false);
  const [selected, setSelected] = useState<ChildStatus | null>(null);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [probe, setProbe] = useState<CameraProbe | null>(null);
  const [probeBusy, setProbeBusy] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);
  const today = new Intl.DateTimeFormat("pt-BR", { weekday: "long", day: "2-digit", month: "long" }).format(new Date()).toUpperCase();
  const children = <section className="children-grid">
    {snapshot.children.map(child => <ChildStatusCard key={child.id} child={child} onOpen={setSelected} />)}
    <button className="add-child-card" onClick={() => setWizardOpen(true)}><span><Plus /></span><strong>Adicionar criança</strong><small>Crie um perfil com limite e cadastro facial próprios</small></button>
  </section>;

  let content: ReactNode;
  if (activeSection === "overview") content = <><StatePanel snapshot={snapshot} />
    <section className="section-heading"><div><h2>Perfis das crianças</h2><p>{snapshot.children.length} {snapshot.children.length === 1 ? "perfil configurado" : "perfis configurados"} neste computador</p></div><button className="text-button" onClick={() => setActiveSection("children")}>Ver detalhes <ChevronRight size={16} /></button></section>
    {children}<section className="bottom-grid">
      <article className="panel"><div className="panel__heading"><div><span className="panel-icon"><CalendarClock /></span><div><h3>Rotina de hoje</h3><p>Horário compartilhado da conta filhos</p></div></div><button className="text-button" onClick={() => setScheduleOpen(true)}>Editar</button></div><Schedule snapshot={snapshot} /></article>
      <article className="panel"><div className="panel__heading"><div><span className="panel-icon panel-icon--violet"><Activity /></span><div><h3>Estado atual</h3><p>Dados lidos do serviço local</p></div></div></div><ul className="activity-list"><li><i className="dot dot--green" /><div><strong>{snapshot.children.length} {snapshot.children.length === 1 ? "perfil configurado" : "perfis configurados"}</strong><span>cadastros protegidos neste computador</span></div></li><li><i className="dot dot--blue" /><div><strong>Câmera {snapshot.camera === "ready" ? "pronta" : snapshot.camera === "busy" ? "em uso" : "indisponível"}</strong><span>sessão {snapshot.session === "active" ? "ativa" : snapshot.session === "locked" ? "bloqueada" : "ausente"}</span></div></li></ul></article>
    </section></>;
  else if (activeSection === "children") content = <><section className="section-heading"><div><h2>Perfis cadastrados</h2><p>Selecione uma criança para trocar a foto, ajustar o limite ou adicionar bônus.</p></div></section>{children}</>;
  else if (activeSection === "schedule") content = <section className="single-column"><article className="panel panel--feature"><div className="panel__heading"><div><span className="panel-icon"><CalendarClock /></span><div><h3>Horário da conta filhos</h3><p>A regra vale para todas as crianças deste computador.</p></div></div><button className="button button--secondary" onClick={() => setScheduleOpen(true)}>Editar horário</button></div><Schedule snapshot={snapshot} /><p className="panel-note">Fora deste período, a sessão infantil permanece bloqueada mesmo quando ainda existe tempo diário.</p></article></section>;
  else if (activeSection === "history") content = snapshot.children.length ? <section className="history-grid">{snapshot.children.map(child => <HistoryCard key={child.id} child={child} />)}</section> : <EmptyState icon={<Activity />} title="Nenhum histórico disponível" text="Cadastre uma criança para começar a acompanhar o uso." />;
  else if (activeSection === "diagnostics") content = <><StatePanel snapshot={snapshot} /><section className="diagnostic-grid"><InfoCard icon={<Database />} title="Dados locais" value="Armazenamento protegido" text="Perfis, fotos e histórico ficam neste computador." /><InfoCard icon={<LockKeyhole />} title="Sessão infantil" value={snapshot.session === "active" ? "Ativa" : snapshot.session === "locked" ? "Bloqueada" : "Ausente"} text={`Última leitura: ${new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" }).format(new Date(snapshot.generatedAt))}`} /><InfoCard icon={<Camera />} title="Reconhecimento" value={snapshot.camera === "ready" ? "Disponível" : snapshot.camera === "busy" ? "Em uso" : "Indisponível"} text="O processamento facial acontece localmente." /></section><section className="camera-diagnostic panel"><div className="panel__heading"><div><span className="panel-icon"><Camera /></span><div><h3>Diagnóstico da câmera</h3><p>Usa a telemetria recente do serviço sem interromper o reconhecimento.</p></div></div><button className="button button--secondary" disabled={probeBusy || snapshot.service !== "online"} onClick={() => { setProbeBusy(true); setProbeError(null); void onProbeCamera().then(setProbe).catch(reason => setProbeError(reason instanceof Error ? reason.message : "Falha no diagnóstico")).finally(() => setProbeBusy(false)); }}><RefreshCw size={15} />{probeBusy ? "Verificando…" : "Executar diagnóstico"}</button></div>{probe && <dl className="probe-results"><div><dt>Câmera</dt><dd>{probe.opened ? "Aberta" : "Indisponível"}</dd></div><div><dt>Quadros úteis</dt><dd>{probe.usable_frames} de {probe.frames}</dd></div><div><dt>Detecções de rosto</dt><dd>{probe.faces_seen}</dd></div><div><dt>Luminosidade média</dt><dd>{probe.mean_brightness === null ? "Sem leitura" : Math.round(probe.mean_brightness)}</dd></div></dl>}{probeError && <p className="form-error" role="alert">{probeError}</p>}</section></>;
  else content = <section className="settings-list"><InfoCard icon={<Users />} title="Perfis infantis" value={`${snapshot.children.length} configurado${snapshot.children.length === 1 ? "" : "s"}`} text="Cada perfil possui fotos e limite próprios." action={<button className="text-button" onClick={() => setActiveSection("children")}>Gerenciar <ChevronRight size={16} /></button>} /><InfoCard icon={<CalendarClock />} title="Horário compartilhado" value={snapshot.curfew.enabled ? `${snapshot.curfew.start} – ${snapshot.curfew.end}` : "Desativado"} text="Aplicado à conta filhos." action={<button className="text-button" onClick={() => setScheduleOpen(true)}>Editar <ChevronRight size={16} /></button>} /><InfoCard icon={<ShieldCheck />} title="Privacidade" value="Processamento local" text="Fotos e vetores faciais não são enviados para a nuvem." /></section>;

  return <div className="admin-shell"><aside className="sidebar">
    <div className="brand"><div className="brand__mark"><Sparkles size={21} /></div><div><strong>FaceKids</strong><span>Painel dos pais</span></div></div>
    <nav aria-label="Seções do painel">{nav.map(([id, Icon, label]) => <button key={id} className={activeSection === id ? "active" : ""} aria-current={activeSection === id ? "page" : undefined} onClick={() => setActiveSection(id)}><Icon size={19} /><span>{label}</span>{id === "children" && <b>{snapshot.children.length}</b>}</button>)}</nav>
    <button className="sidebar__help" onClick={() => setActiveSection("diagnostics")}><CircleHelp size={20} /><div><strong>Precisa de ajuda?</strong><span>Confira o diagnóstico</span></div><ChevronRight size={18} /></button>
    <div className="parent-chip"><div className="parent-chip__avatar">R</div><div><strong>Responsável</strong><span>Administrador</span></div></div>
  </aside><main className="admin-content">
    {backendError && <div className="backend-alert" role="alert"><strong>Serviço não conectado</strong><span>{backendError}</span></div>}
    <header className="page-header"><div><span className="eyebrow">{today}</span><h1>{titles[activeSection][0]}</h1><p>{titles[activeSection][1]}</p></div>{(activeSection === "overview" || activeSection === "children") && <button className="button button--primary" onClick={() => setWizardOpen(true)}><Plus size={18} /> Nova criança</button>}</header>{content}
  </main>{wizardOpen && <EnrollmentWizard enrollment={enrollment} onEnroll={onEnrollChild} onCancelEnrollment={onCancelEnrollment} onClose={() => setWizardOpen(false)} />}{selected && <ProfilePhotoManager child={selected} enrollment={enrollment} loadPhotos={onListPhotos} selectPhoto={onSelectPhoto} renameChild={onRenameChild} deleteChild={onDeleteChild} startCapture={onStartEnrollment} cancelCapture={onCancelEnrollment} setDailyLimit={onSetDailyLimit} addBonus={onAddBonus} onClose={() => setSelected(null)} />}{scheduleOpen && <ScheduleEditor current={snapshot.curfew} onSave={onSetCurfew} onClose={() => setScheduleOpen(false)} />}</div>;
}

function Schedule({ snapshot }: { snapshot: SystemSnapshot }) { return <div className={`schedule${snapshot.curfew.enabled ? "" : " schedule--disabled"}`}><span>{snapshot.curfew.start}</span><div><i /><b>{snapshot.curfew.enabled ? "Uso permitido" : "Controle desativado"}</b></div><span>{snapshot.curfew.end}</span></div>; }
function InfoCard({ icon, title, value, text, action }: { icon: ReactNode; title: string; value: string; text: string; action?: ReactNode }) { return <article className="info-card"><span className="panel-icon">{icon}</span><div><small>{title}</small><strong>{value}</strong><p>{text}</p></div>{action}</article>; }
function EmptyState({ icon, title, text }: { icon: ReactNode; title: string; text: string }) { return <section className="empty-state"><span>{icon}</span><strong>{title}</strong><p>{text}</p></section>; }

function HistoryCard({ child }: { child: ChildStatus }) {
  const total = child.usageHistory.reduce((sum, day) => sum + day.usedSeconds, 0);
  const daysWithUse = child.usageHistory.filter(day => day.usedSeconds > 0).length;
  const average = daysWithUse ? Math.round(total / daysWithUse) : 0;
  return <article className="panel"><div className="panel__heading"><div><span className="avatar avatar--small">{child.initials}</span><div><h3>{child.name}</h3><p>Tempo usado por dia</p></div></div></div><dl className="history-summary"><div><dt>Total em 7 dias</dt><dd>{formatTime(total)}</dd></div><div><dt>Média nos dias de uso</dt><dd>{formatTime(average)}</dd></div></dl><div className="history-list">{child.usageHistory.map(day => { const exceeded = day.usedSeconds > child.dailyLimitSeconds; return <div key={day.date} className={exceeded ? "history-day--exceeded" : ""}><time dateTime={day.date}>{new Intl.DateTimeFormat("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit", timeZone: "UTC" }).format(new Date(`${day.date}T00:00:00Z`))}</time><span><i style={{ width: `${Math.min(100, day.usedSeconds / child.dailyLimitSeconds * 100)}%` }} /></span><strong>{day.usedSeconds ? formatTime(day.usedSeconds) : "Sem uso"}{exceeded && <em>acima do limite</em>}</strong></div>; })}</div></article>;
}
