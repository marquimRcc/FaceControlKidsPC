import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Camera, Check, ShieldCheck, UserRound } from "lucide-react";

const steps = ["Perfil", "Reconhecimento", "Confirmar"];

export function EnrollmentWizard({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [minutes, setMinutes] = useState(120);
  const [samples, setSamples] = useState(7);

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="wizard" role="dialog" aria-modal="true" aria-labelledby="wizard-title">
        <header><div><span className="eyebrow">NOVO PERFIL</span><h2 id="wizard-title">Cadastrar criança</h2><p>Os dados e vetores faciais ficam somente neste computador.</p></div><button className="close-button" onClick={onClose} aria-label="Fechar">×</button></header>
        <ol className="steps">{steps.map((label, index) => <li key={label} className={index <= step ? "active" : ""}><span>{index < step ? <Check size={15} /> : index + 1}</span><b>{label}</b></li>)}</ol>

        <div className="wizard__content">
          {step === 0 && <div className="profile-step"><div className="profile-avatar"><UserRound /></div><label>Nome da criança<input autoFocus value={name} onChange={event => setName(event.target.value)} placeholder="Como ela deve ser chamada?" /></label><label>Limite diário<div className="choice-row">{[60, 90, 120, 180].map(value => <button key={value} className={minutes === value ? "selected" : ""} onClick={() => setMinutes(value)}>{value < 120 ? `${value} min` : `${value / 60} horas`}</button>)}</div></label><aside className="privacy-note"><ShieldCheck /><div><strong>Privacidade por padrão</strong><span>Nenhuma foto ou vídeo será salvo. O sistema guarda apenas representações matemáticas do rosto.</span></div></aside></div>}
          {step === 1 && <div className="camera-step"><div className="camera-preview"><div className="face-guide"><span /><span /><span /><span /></div><div className="camera-person"><UserRound /></div><span className="camera-badge"><i /> Um rosto detectado</span></div><div className="capture-status"><div><strong>Mantenha o rosto centralizado</strong><span>Vire levemente a cabeça entre as capturas</span></div><b aria-live="polite">{samples}/12</b></div><div className="sample-track"><i style={{ width: `${samples / 12 * 100}%` }} /></div><button className="button button--secondary" disabled={samples >= 12} onClick={() => setSamples(Math.min(12, samples + 1))}><Camera size={18} /> {samples >= 12 ? "Captura concluída" : "Simular próxima amostra"}</button></div>}
          {step === 2 && <div className="confirmation-step"><span className="success-seal"><Check /></span><h3>Pronto para criar o perfil</h3><p>Confira os dados antes de salvar no serviço protegido.</p><dl><div><dt>Nome</dt><dd>{name || "Nova criança"}</dd></div><div><dt>Limite diário</dt><dd>{minutes} minutos</dd></div><div><dt>Cadastro facial</dt><dd>{samples} amostras válidas</dd></div></dl></div>}
        </div>

        <footer><button className="button button--ghost" onClick={step === 0 ? onClose : () => setStep(step - 1)}>{step > 0 && <ArrowLeft size={17} />}{step === 0 ? "Cancelar" : "Voltar"}</button><button className="button button--primary" disabled={(step === 0 && !name.trim()) || (step === 1 && samples < 12)} onClick={step === 2 ? onClose : () => setStep(step + 1)}>{step === 2 ? "Criar perfil" : "Continuar"}{step < 2 && <ArrowRight size={17} />}</button></footer>
      </section>
    </div>
  );
}
