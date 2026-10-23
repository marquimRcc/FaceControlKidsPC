import { useEffect, useState } from "react";
import type { EnrollmentStatus } from "@facekids/contracts";
import { ArrowRight, Check, ShieldCheck, UserRound } from "lucide-react";

const steps = ["Perfil", "Reconhecimento", "Confirmar"];

export function EnrollmentWizard({ enrollment, onEnroll, onCancelEnrollment, onClose }: {
  enrollment: EnrollmentStatus | null;
  onEnroll: (name: string, minutes: number) => Promise<number>;
  onCancelEnrollment: () => Promise<void>;
  onClose: () => void;
}) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [minutes, setMinutes] = useState(120);
  const [childId, setChildId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const samples = childId && enrollment?.childId === childId ? enrollment.samples : 0;
  const requiredSamples = enrollment?.requiredSamples ?? 12;

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (step === 1 && enrollment?.state !== "complete") {
          void onCancelEnrollment().finally(onClose);
        } else {
          onClose();
        }
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [enrollment?.state, onCancelEnrollment, onClose, step]);

  const beginEnrollment = async () => {
    setBusy(true);
    setError(null);
    try {
      const id = await onEnroll(name.trim(), minutes);
      setChildId(id);
      setStep(1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível iniciar o cadastro");
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (step === 1 && enrollment?.state !== "complete") await onCancelEnrollment();
    onClose();
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="wizard" role="dialog" aria-modal="true" aria-labelledby="wizard-title">
        <header><div><span className="eyebrow">NOVO PERFIL</span><h2 id="wizard-title">Cadastrar criança</h2><p>Os dados e vetores faciais ficam somente neste computador.</p></div><button className="close-button" onClick={() => void cancel()} aria-label="Fechar">×</button></header>
        <ol className="steps">{steps.map((label, index) => <li key={label} className={index <= step ? "active" : ""}><span>{index < step ? <Check size={15} /> : index + 1}</span><b>{label}</b></li>)}</ol>

        <div className="wizard__content">
          {step === 0 && <div className="profile-step"><div className="profile-avatar"><UserRound /></div><label>Nome da criança<input autoFocus value={name} onChange={event => setName(event.target.value)} placeholder="Como ela deve ser chamada?" /></label><label>Limite diário<div className="choice-row">{[60, 90, 120, 180].map(value => <button key={value} className={minutes === value ? "selected" : ""} onClick={() => setMinutes(value)}>{value < 120 ? `${value} min` : `${value / 60} horas`}</button>)}</div></label><aside className="privacy-note"><ShieldCheck /><div><strong>Privacidade por padrão</strong><span>Nenhuma foto ou vídeo será salvo. O sistema guarda apenas representações matemáticas do rosto.</span></div></aside></div>}
          {step === 1 && <div className="camera-step"><div className="camera-preview"><div className="face-guide"><span /><span /><span /><span /></div><div className="camera-person"><UserRound /></div><span className="camera-badge"><i /> {enrollment?.state === "complete" ? "Cadastro concluído" : "Câmera protegida ativa"}</span></div><div className="capture-status"><div><strong>Mantenha apenas um rosto centralizado</strong><span>Vire levemente a cabeça; as imagens não são salvas</span></div><b aria-live="polite">{samples}/{requiredSamples}</b></div><div className="sample-track"><i style={{ width: `${samples / requiredSamples * 100}%` }} /></div>{enrollment?.state === "error" && <p className="form-error">{enrollment.error}</p>}</div>}
          {step === 2 && <div className="confirmation-step"><span className="success-seal"><Check /></span><h3>Perfil criado</h3><p>Os vetores faciais foram salvos pelo serviço protegido.</p><dl><div><dt>Nome</dt><dd>{name}</dd></div><div><dt>Limite diário</dt><dd>{minutes} minutos</dd></div><div><dt>Cadastro facial</dt><dd>{samples} amostras válidas</dd></div></dl></div>}
          {error && <p className="form-error" role="alert">{error}</p>}
        </div>

        <footer><button className="button button--ghost" onClick={() => void cancel()}>{step === 0 ? "Cancelar" : "Fechar"}</button><button className="button button--primary" disabled={busy || (step === 0 && !name.trim()) || (step === 1 && enrollment?.state !== "complete")} onClick={step === 0 ? () => void beginEnrollment() : step === 1 ? () => setStep(2) : onClose}>{busy ? "Iniciando…" : step === 2 ? "Concluir" : "Continuar"}{step < 2 && <ArrowRight size={17} />}</button></footer>
      </section>
    </div>
  );
}
