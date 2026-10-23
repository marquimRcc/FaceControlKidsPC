import { useEffect, useState } from "react";
import type { ChildStatus, EnrollmentStatus, ProfilePhoto } from "@facekids/contracts";
import { Camera, Check, Clock3, Gift, Image as ImageIcon, Pencil, ShieldCheck, X } from "lucide-react";

export function ProfilePhotoManager({ child, enrollment, loadPhotos, selectPhoto, renameChild, startCapture, cancelCapture, setDailyLimit, addBonus, onClose }: {
  child: ChildStatus;
  enrollment: EnrollmentStatus | null;
  loadPhotos: (childId: number) => Promise<ProfilePhoto[]>;
  selectPhoto: (childId: number, photoId: number) => Promise<void>;
  renameChild: (childId: number, name: string) => Promise<void>;
  startCapture: (childId: number) => Promise<void>;
  cancelCapture: () => Promise<void>;
  setDailyLimit: (childId: number, minutes: number) => Promise<void>;
  addBonus: (childId: number, minutes: number) => Promise<void>;
  onClose: () => void;
}) {
  const [photos, setPhotos] = useState<ProfilePhoto[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [name, setName] = useState(child.name);
  const [savedName, setSavedName] = useState(child.name);
  const [limitMinutes, setLimitMinutes] = useState(child.dailyLimitSeconds / 60);
  const ownEnrollment = enrollment?.childId === child.id ? enrollment : null;

  const refresh = async () => {
    try { setPhotos(await loadPhotos(child.id)); setError(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao carregar fotos"); }
  };
  useEffect(() => { void refresh(); }, [child.id, ownEnrollment?.state]);

  const choose = async (photoId: number) => {
    setBusy(true);
    try { await selectPhoto(child.id, photoId); await refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao escolher foto"); }
    finally { setBusy(false); }
  };
  const capture = async () => {
    setBusy(true);
    try { await startCapture(child.id); setError(null); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao iniciar câmera"); }
    finally { setBusy(false); }
  };
  const updateLimit = async (minutes: number) => {
    setBusy(true);
    try {
      await setDailyLimit(child.id, minutes);
      setLimitMinutes(minutes);
      setNotice(`Limite diário alterado para ${minutes} minutos.`);
      setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao alterar limite"); }
    finally { setBusy(false); }
  };
  const updateName = async () => {
    const cleaned = name.trim();
    if (!cleaned || cleaned.length > 80) {
      setError("Informe um nome com até 80 caracteres.");
      return;
    }
    setBusy(true);
    try {
      await renameChild(child.id, cleaned);
      setName(cleaned);
      setSavedName(cleaned);
      setNotice("Nome atualizado.");
      setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao alterar nome"); }
    finally { setBusy(false); }
  };
  const grantBonus = async (minutes: number) => {
    setBusy(true);
    try {
      await addBonus(child.id, minutes);
      setNotice(`Bônus de ${minutes} minutos concedido para hoje.`);
      setError(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao conceder bônus"); }
    finally { setBusy(false); }
  };
  const close = async () => {
    if (ownEnrollment?.state === "capturing") await cancelCapture();
    onClose();
  };

  return <div className="modal-backdrop" role="presentation">
    <section className="photo-manager" role="dialog" aria-modal="true" aria-labelledby="photo-manager-title">
      <header><div><span className="eyebrow">PERFIL DE {name.toUpperCase()}</span><h2 id="photo-manager-title">Gerenciar perfil</h2><p>Edite o nome, ajuste o tempo e escolha a foto do painel.</p></div><button className="close-button" onClick={() => void close()} aria-label="Fechar"><X size={17} /></button></header>
      <div className="photo-manager__content">
        <form className="name-editor" onSubmit={event => { event.preventDefault(); void updateName(); }}><label htmlFor="child-name"><Pencil /><span><strong>Nome da criança</strong><small>Exibido no painel e na tela de boas-vindas</small></span></label><div><input id="child-name" value={name} maxLength={80} disabled={busy} onChange={event => setName(event.target.value)} autoComplete="off" /><button className="button button--secondary" type="submit" disabled={busy || !name.trim() || name.trim() === savedName}>Salvar nome</button></div></form>
        <section className="profile-controls" aria-label="Tempo de uso"><div><Clock3 /><span><strong>Limite diário</strong><small>Atual: {limitMinutes} minutos</small></span></div><div className="compact-choices">{[60, 90, 120, 180].map(minutes => <button key={minutes} disabled={busy} className={limitMinutes === minutes ? "selected" : ""} onClick={() => void updateLimit(minutes)}>{minutes < 120 ? `${minutes} min` : `${minutes / 60} h`}</button>)}</div></section>
        <section className="profile-controls" aria-label="Bônus de hoje"><div><Gift /><span><strong>Bônus para hoje</strong><small>Acumula até 8 horas no dia</small></span></div><div className="compact-choices">{[15, 30, 60].map(minutes => <button key={minutes} disabled={busy} onClick={() => void grantBonus(minutes)}>+{minutes} min</button>)}</div></section>
        <div className="subsection-heading"><strong>Foto exibida no painel</strong><span>Guardada somente neste computador</span></div>
        {photos.length ? <div className="photo-grid">{photos.map(photo => <button key={photo.id} disabled={busy} className={photo.selected ? "selected" : ""} onClick={() => void choose(photo.id)}><img src={photo.dataUrl} alt={`Foto de ${name}`} />{photo.selected && <span><Check size={14} /> Em uso</span>}</button>)}</div> : <div className="empty-photos"><ImageIcon /><strong>Nenhuma foto armazenada</strong><span>Capture fotos pela câmera para escolher uma imagem do perfil.</span></div>}
        {ownEnrollment?.state === "capturing" && <div className="capture-progress"><Camera /><div><strong>Capturando novas fotos e renovando o reconhecimento</strong><span>{ownEnrollment.samples}/{ownEnrollment.requiredSamples} amostras — mantenha apenas a criança diante da câmera</span><i><b style={{width:`${ownEnrollment.samples / ownEnrollment.requiredSamples * 100}%`}} /></i></div></div>}
        {ownEnrollment?.state === "complete" && <div className="capture-complete"><Check /> Novas fotos adicionadas. Escolha uma acima.</div>}
        {error && <p className="form-error" role="alert">{error}</p>}
        {notice && <p className="form-notice" role="status"><Check size={15} />{notice}</p>}
        <aside className="privacy-note"><ShieldCheck /><div><strong>Fotos separadas da biometria</strong><span>Estas imagens servem somente para o painel. O reconhecimento continua usando vetores matemáticos.</span></div></aside>
      </div>
      <footer><button className="button button--ghost" onClick={() => void close()}>Fechar</button><button className="button button--primary" disabled={busy || ownEnrollment?.state === "capturing"} onClick={() => void capture()}><Camera size={17} />{photos.length ? "Capturar outras fotos" : "Capturar fotos"}</button></footer>
    </section>
  </div>;
}
