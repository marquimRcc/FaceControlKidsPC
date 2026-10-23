import { useState } from "react";
import { Clock3, X } from "lucide-react";

export function ScheduleEditor({ current, onSave, onClose }: {
  current: { enabled: boolean; start: string; end: string };
  onSave: (input: { enabled: boolean; start: string; end: string }) => Promise<void>;
  onClose: () => void;
}) {
  const [enabled, setEnabled] = useState(current.enabled);
  const [start, setStart] = useState(current.start);
  const [end, setEnd] = useState(current.end);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setBusy(true);
    try { await onSave({ enabled, start, end }); onClose(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao salvar horário"); }
    finally { setBusy(false); }
  };
  return <div className="modal-backdrop" role="presentation"><section className="schedule-editor" role="dialog" aria-modal="true" aria-labelledby="schedule-title">
    <header><div><span className="eyebrow">CONTA FILHOS</span><h2 id="schedule-title">Horário permitido</h2><p>Este horário vale para todas as crianças desta conta.</p></div><button className="close-button" onClick={onClose} aria-label="Fechar"><X size={17} /></button></header>
    <div className="schedule-editor__content"><label className="toggle-row"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} /><span><strong>Aplicar horário de uso</strong><small>Fora do intervalo, a sessão permanece bloqueada.</small></span></label><div className="time-inputs"><label>Começa às<input type="time" value={start} onChange={event => setStart(event.target.value)} disabled={!enabled} /></label><Clock3 /><label>Termina às<input type="time" value={end} onChange={event => setEnd(event.target.value)} disabled={!enabled} /></label></div>{error && <p className="form-error" role="alert">{error}</p>}</div>
    <footer><button className="button button--ghost" onClick={onClose}>Cancelar</button><button className="button button--primary" disabled={busy || !start || !end} onClick={() => void save()}>{busy ? "Salvando…" : "Salvar horário"}</button></footer>
  </section></div>;
}
