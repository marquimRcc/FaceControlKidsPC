import type { SystemSnapshot } from "@facekids/contracts";
import { StatusPill, TimeRing } from "@facekids/ui";
import { BellRing, Clock3, ScanFace, ShieldCheck, Sparkles, SunMedium } from "lucide-react";

export function ChildWelcome({ snapshot }: { snapshot: SystemSnapshot }) {
  const child = snapshot.children.find(item => item.isPresent) ?? snapshot.children[0];
  const today = new Intl.DateTimeFormat("pt-BR", { weekday: "long" }).format(new Date());
  const greeting = new Date().getHours() < 12 ? "Bom dia" : new Date().getHours() < 18 ? "Boa tarde" : "Boa noite";
  if (!child) return <main className="welcome-shell">
    <div className="welcome-orb welcome-orb--one" /><div className="welcome-orb welcome-orb--two" />
    <section className="welcome-card welcome-card--waiting">
      <header className="welcome-card__brand"><span><Sparkles /></span><strong>FaceKids</strong><StatusPill tone="warn">Identificando</StatusPill></header>
      <div className="scan-face"><ScanFace /></div><span className="eyebrow">AGUARDANDO RECONHECIMENTO</span>
      <h1>Olhe para a câmera</h1><p className="welcome-lead">Mantenha somente um rosto visível para consultar seu tempo.</p>
      <div className="welcome-note"><ShieldCheck /><span>Nenhuma imagem é enviada para a internet.</span></div>
    </section>
    <div className="welcome-weather"><SunMedium /><span>{greeting}</span><b>•</b><span>{today}</span></div>
  </main>;
  const schedule = snapshot.curfew.enabled
    ? `${snapshot.curfew.start} – ${snapshot.curfew.end}` : "Sem restrição hoje";
  return <main className="welcome-shell">
    <div className="welcome-orb welcome-orb--one" /><div className="welcome-orb welcome-orb--two" />
    <section className="welcome-card">
      <header className="welcome-card__brand"><span><Sparkles /></span><strong>FaceKids</strong><StatusPill tone="ok">Proteção ativa</StatusPill></header>
      <div className={`welcome-avatar${child.avatarPhoto ? " welcome-avatar--photo" : ""}`}>{child.avatarPhoto ? <img src={child.avatarPhoto} alt={`Foto de ${child.name}`} /> : child.initials}<i /></div>
      <span className="eyebrow">ROSTO RECONHECIDO</span>
      <h1>Olá, {child.name}! <span>👋</span></h1>
      <p className="welcome-lead">Tudo pronto para você aproveitar seu tempo hoje.</p>
      <TimeRing remaining={child.remainingSeconds} total={child.dailyLimitSeconds + child.bonusSeconds} size="large" />
      <div className="welcome-facts"><div><Clock3 /><span><small>Horário de hoje</small><strong>{schedule}</strong></span></div><div><BellRing /><span><small>Próximo aviso</small><strong>15 min antes do fim</strong></span></div></div>
      <button className="button button--primary welcome-button" onClick={() => window.close()}>Começar agora</button>
      <div className="welcome-note"><ShieldCheck /><span>Seu reconhecimento acontece somente neste computador.</span></div>
    </section>
    <div className="welcome-weather"><SunMedium /><span>{greeting}</span><b>•</b><span>{today}</span></div>
  </main>;
}
