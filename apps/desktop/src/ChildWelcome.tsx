import type { SystemSnapshot } from "@facekids/contracts";
import { StatusPill, TimeRing } from "@facekids/ui";
import { BellRing, Clock3, ShieldCheck, Sparkles, SunMedium } from "lucide-react";

export function ChildWelcome({ snapshot }: { snapshot: SystemSnapshot }) {
  const child = snapshot.children.find(item => item.isPresent) ?? snapshot.children[0]!;
  return <main className="welcome-shell">
    <div className="welcome-orb welcome-orb--one" /><div className="welcome-orb welcome-orb--two" />
    <section className="welcome-card">
      <header className="welcome-card__brand"><span><Sparkles /></span><strong>FaceKids</strong><StatusPill tone="ok">Proteção ativa</StatusPill></header>
      <div className="welcome-avatar">{child.initials}<i /></div>
      <span className="eyebrow">ROSTO RECONHECIDO</span>
      <h1>Olá, {child.name}! <span>👋</span></h1>
      <p className="welcome-lead">Tudo pronto para você aproveitar seu tempo hoje.</p>
      <TimeRing remaining={child.remainingSeconds} total={child.dailyLimitSeconds + child.bonusSeconds} size="large" />
      <div className="welcome-facts"><div><Clock3 /><span><small>Horário de hoje</small><strong>{snapshot.curfew.start} – {snapshot.curfew.end}</strong></span></div><div><BellRing /><span><small>Próximo aviso</small><strong>15 min restantes</strong></span></div></div>
      <button className="button button--primary welcome-button">Começar agora</button>
      <div className="welcome-note"><ShieldCheck /><span>Seu reconhecimento acontece somente neste computador.</span></div>
    </section>
    <div className="welcome-weather"><SunMedium /><span>Bom dia</span><b>•</b><span>Quinta-feira</span></div>
  </main>;
}
