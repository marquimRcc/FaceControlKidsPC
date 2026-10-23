import { useEffect, useState } from "react";
import type { ChildStatus, EnrollmentStatus, ProfilePhoto } from "@facekids/contracts";
import { Camera, Check, Image as ImageIcon, ShieldCheck, X } from "lucide-react";

export function ProfilePhotoManager({ child, enrollment, loadPhotos, selectPhoto, startCapture, cancelCapture, onClose }: {
  child: ChildStatus;
  enrollment: EnrollmentStatus | null;
  loadPhotos: (childId: number) => Promise<ProfilePhoto[]>;
  selectPhoto: (childId: number, photoId: number) => Promise<void>;
  startCapture: (childId: number) => Promise<void>;
  cancelCapture: () => Promise<void>;
  onClose: () => void;
}) {
  const [photos, setPhotos] = useState<ProfilePhoto[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
  const close = async () => {
    if (ownEnrollment?.state === "capturing") await cancelCapture();
    onClose();
  };

  return <div className="modal-backdrop" role="presentation">
    <section className="photo-manager" role="dialog" aria-modal="true" aria-labelledby="photo-manager-title">
      <header><div><span className="eyebrow">PERFIL DE {child.name.toUpperCase()}</span><h2 id="photo-manager-title">Foto exibida no painel</h2><p>Escolha uma das fotos guardadas somente neste computador.</p></div><button className="close-button" onClick={() => void close()} aria-label="Fechar"><X size={17} /></button></header>
      <div className="photo-manager__content">
        {photos.length ? <div className="photo-grid">{photos.map(photo => <button key={photo.id} disabled={busy} className={photo.selected ? "selected" : ""} onClick={() => void choose(photo.id)}><img src={photo.dataUrl} alt={`Foto de ${child.name}`} />{photo.selected && <span><Check size={14} /> Em uso</span>}</button>)}</div> : <div className="empty-photos"><ImageIcon /><strong>Nenhuma foto armazenada</strong><span>Capture fotos pela câmera para escolher uma imagem do perfil.</span></div>}
        {ownEnrollment?.state === "capturing" && <div className="capture-progress"><Camera /><div><strong>Capturando novas fotos e renovando o reconhecimento</strong><span>{ownEnrollment.samples}/{ownEnrollment.requiredSamples} amostras — mantenha apenas a criança diante da câmera</span><i><b style={{width:`${ownEnrollment.samples / ownEnrollment.requiredSamples * 100}%`}} /></i></div></div>}
        {ownEnrollment?.state === "complete" && <div className="capture-complete"><Check /> Novas fotos adicionadas. Escolha uma acima.</div>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <aside className="privacy-note"><ShieldCheck /><div><strong>Fotos separadas da biometria</strong><span>Estas imagens servem somente para o painel. O reconhecimento continua usando vetores matemáticos.</span></div></aside>
      </div>
      <footer><button className="button button--ghost" onClick={() => void close()}>Fechar</button><button className="button button--primary" disabled={busy || ownEnrollment?.state === "capturing"} onClick={() => void capture()}><Camera size={17} />{photos.length ? "Capturar outras fotos" : "Capturar fotos"}</button></footer>
    </section>
  </div>;
}
