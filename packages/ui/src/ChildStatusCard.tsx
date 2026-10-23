import type { ChildStatus } from "@facekids/contracts";
import { CheckCircle2, Clock3, UserRoundCheck } from "lucide-react";
import { formatTime, TimeRing } from "./TimeRing";

interface ChildStatusCardProps {
  child: ChildStatus;
  onOpen?: (child: ChildStatus) => void;
  compact?: boolean;
}

export function ChildStatusCard({ child, onOpen, compact = false }: ChildStatusCardProps) {
  return (
    <article className={`child-card${compact ? " child-card--compact" : ""}`}>
      <header className="child-card__header">
        <div className="avatar" aria-hidden="true">{child.initials}</div>
        <div>
          <span className="eyebrow">Perfil {child.id}</span>
          <h3>{child.name}</h3>
        </div>
        <span className={`presence${child.isPresent ? " presence--online" : ""}`}>
          {child.isPresent ? "Presente" : "Ausente"}
        </span>
      </header>
      <div className="child-card__body">
        <TimeRing remaining={child.remainingSeconds} total={child.dailyLimitSeconds + child.bonusSeconds} />
        <dl className="child-card__facts">
          <div><dt><Clock3 size={15} /> Limite diário</dt><dd>{formatTime(child.dailyLimitSeconds)}</dd></div>
          <div><dt><UserRoundCheck size={15} /> Cadastro facial</dt><dd>{child.enrollmentSamples} amostras</dd></div>
          <div><dt><CheckCircle2 size={15} /> Bônus hoje</dt><dd>{formatTime(child.bonusSeconds)}</dd></div>
        </dl>
      </div>
      {onOpen && <button className="button button--ghost button--full" onClick={() => onOpen(child)}>Gerenciar perfil</button>}
    </article>
  );
}
