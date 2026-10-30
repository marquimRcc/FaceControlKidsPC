"""Utilitários para processamento e corte de fotos de avatar das crianças."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .platform_paths import application_data_dir

logger = logging.getLogger("FaceKidsAvatar")
AVATAR_DIR = application_data_dir() / "fotos"


def ensure_avatar_dir() -> Path:
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    return AVATAR_DIR


def load_image_any_path(path: str) -> Optional[np.ndarray]:
    """Carrega imagem de qualquer caminho no Windows (incluindo acentos e espacos)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        arr = np.frombuffer(data, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as e:
        logger.warning("Falha ao abrir arquivo de imagem '%s': %s", path, e)
        return None


def save_child_photo(child_id: int, frame: np.ndarray, face_box: Optional[list | np.ndarray] = None, store=None) -> Optional[Path]:
    """Salva a foto cortada do rosto da crianca e gera o PNG circular correspondente."""
    try:
        ensure_avatar_dir()
        H, W = frame.shape[:2]

        if face_box is not None and len(face_box) >= 4:
            x, y, w, h = int(face_box[0]), int(face_box[1]), int(face_box[2]), int(face_box[3])
            # Margem de 30% ao redor do rosto para incluir cabelo e contorno
            mx, my = int(w * 0.30), int(h * 0.30)
            x1, y1 = max(0, x - mx), max(0, y - my)
            x2, y2 = min(W, x + w + mx), min(H, y + h + my)
            cropped = frame[y1:y2, x1:x2]
        else:
            cropped = frame

        if cropped is None or cropped.size == 0:
            return None

        # 1. Salvar JPEG original cortado
        jpg_path = AVATAR_DIR / f"crianca_{child_id}.jpg"
        cv2.imwrite(str(jpg_path), cropped)

        # 2. Gerar versão circular em PNG transparente de 120x120 para a UI
        circle_png = generate_circular_png(cropped, 120)
        png_path = AVATAR_DIR / f"crianca_{child_id}_avatar.png"
        cv2.imwrite(str(png_path), circle_png)

        # 3. Salvar no banco SQLite se store for fornecido
        if store is not None and hasattr(store, "add_profile_photo"):
            try:
                ok_enc, buf_enc = cv2.imencode(".jpg", cropped)
                if ok_enc:
                    store.add_profile_photo(child_id, buf_enc.tobytes(), select=True)
            except Exception as e:
                logger.debug("Aviso ao salvar profile_photo no SQLite: %s", e)

        logger.info("Avatar da crianca %d salvo com sucesso em %s", child_id, png_path)
        return png_path
    except Exception as e:
        logger.warning("Falha ao salvar avatar da crianca %d: %s", child_id, e)
        return None


def generate_circular_png(bgr_img: np.ndarray, size: int = 120) -> np.ndarray:
    """Recorta quadrado central, escala e aplica mascara circular com borda suave."""
    h, w = bgr_img.shape[:2]
    min_dim = min(h, w)
    crop_x = (w - min_dim) // 2
    crop_y = (h - min_dim) // 2
    square = bgr_img[crop_y : crop_y + min_dim, crop_x : crop_x + min_dim]
    resized = cv2.resize(square, (size, size), interpolation=cv2.INTER_AREA)

    # Canal Alpha transparente
    bgra = cv2.cvtColor(resized, cv2.COLOR_BGR2BGRA)
    mask = np.zeros((size, size), dtype=np.uint8)
    radius = size // 2 - 2
    cv2.circle(mask, (size // 2, size // 2), radius, 255, -1, cv2.LINE_AA)
    bgra[:, :, 3] = mask

    # Borda circular estilizada (Azul vibrante/ciano moderno: B=240, G=180, R=56)
    cv2.circle(bgra, (size // 2, size // 2), radius, (240, 180, 56, 255), 3, cv2.LINE_AA)
    return bgra


class PhotoUpdateResult:
    """Resultado detalhado da atualizacao de foto."""
    def __init__(self, success: bool, message: str, avatar_path: Optional[Path] = None):
        self.success = success
        self.message = message
        self.avatar_path = avatar_path

    def __bool__(self) -> bool:
        return self.success

    def __iter__(self):
        yield self.success
        yield self.message


def set_child_photo_from_file(
    child_id: int,
    file_path: str,
    models_dir: Optional[Path] = None,
    store=None,
    update_biometrics: bool = True,
) -> PhotoUpdateResult:
    """Define a foto da crianca a partir de um arquivo do computador e extrai biometria se possivel."""
    img = load_image_any_path(file_path)
    if img is None or img.size == 0:
        return PhotoUpdateResult(False, "Não foi possível carregar a imagem selecionada.")

    face_box = None
    bio_msg = ""
    if models_dir is not None:
        try:
            from .recognition import Recognizer
            rec = Recognizer(models_dir)
            faces = rec.faces(img)
            if len(faces) >= 1:
                face_box = max(faces, key=lambda f: float(f[2]) * float(f[3]))
                if update_biometrics and store is not None:
                    feat = rec.features(img, face_box)
                    store.add_embedding(child_id, feat)
                    bio_msg = " Rosto detectado e biometria atualizada com sucesso!"
                    logger.info("Novo embedding extraido e adicionado da foto para a crianca %d", child_id)
            else:
                bio_msg = " Foto salva como avatar (nenhum rosto nítido detectado para biometria)."
        except Exception as e:
            logger.warning("Aviso ao extrair biometria da foto selecionada: %s", e)
            bio_msg = f" Foto salva como avatar (aviso biometria: {e})."

    res = save_child_photo(child_id, img, face_box, store=store)
    if res is not None:
        return PhotoUpdateResult(True, f"Foto atualizada!{bio_msg}", res)
    return PhotoUpdateResult(False, "Falha ao processar e salvar imagem recortada.")


def remove_child_avatar_files(child_id: int) -> bool:
    """Remove os arquivos de foto e avatar da crianca do disco."""
    removed = False
    for fname in [f"crianca_{child_id}_avatar.png", f"crianca_{child_id}.jpg"]:
        p = AVATAR_DIR / fname
        if p.exists():
            try:
                p.unlink()
                removed = True
            except Exception as e:
                logger.warning("Falha ao remover arquivo %s: %s", p, e)
    return removed


def get_child_avatar_path(child_id: int) -> Optional[Path]:
    """Retorna o caminho do PNG circular da crianca, gerando-o a partir do JPG ou SQLite se necessario."""
    ensure_avatar_dir()
    png = AVATAR_DIR / f"crianca_{child_id}_avatar.png"
    if png.exists() and png.stat().st_size > 0:
        return png

    # 1. Se existir JPG oficial, gera a versao circular em PNG compativel com Tkinter
    jpg = AVATAR_DIR / f"crianca_{child_id}.jpg"
    if jpg.exists() and jpg.stat().st_size > 0:
        img = load_image_any_path(str(jpg))
        if img is not None and img.size > 0:
            circle = generate_circular_png(img, 120)
            cv2.imwrite(str(png), circle)
            return png

    # 2. Se houver foto selecionada no banco SQLite (profile_photos), exporta e gera o PNG
    try:
        from .children_pilot import child_pilot_database
        from .storage import Storage
        db_path = child_pilot_database()
        if db_path.exists():
            store = Storage(db_path)
            try:
                photo_bytes = store.selected_profile_photo(child_id)
                if not photo_bytes:
                    photos = store.profile_photos(child_id)
                    if photos:
                        photo_bytes = photos[0][1]
                if photo_bytes:
                    arr = np.frombuffer(photo_bytes, dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if img is not None and img.size > 0:
                        cv2.imwrite(str(jpg), img)
                        circle = generate_circular_png(img, 120)
                        cv2.imwrite(str(png), circle)
                        return png
            finally:
                store.close()
    except Exception as e:
        logger.debug("Nao foi possivel carregar foto da crianca %d do SQLite: %s", child_id, e)

    return None

def get_child_samples_dir(child_id: int) -> Path:
    d = AVATAR_DIR / f"amostras_{child_id}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_child_sample_photos(child_id: int, store=None) -> list[dict]:
    """Retorna lista das fotos das amostras da crianca (ate 12 fotos)."""
    samples = []
    s_dir = AVATAR_DIR / f"amostras_{child_id}"

    # Identifica indice da foto atualmente selecionada
    selected_idx = 1
    sel_file = s_dir / "selecionada.txt"
    if sel_file.exists():
        try:
            selected_idx = int(sel_file.read_text().strip())
        except Exception:
            pass
    elif store is not None and hasattr(store, "get_setting"):
        try:
            val = store.get_setting(f"selected_sample_{child_id}")
            if val:
                selected_idx = int(val)
        except Exception:
            pass

    if s_dir.exists():
        for i in range(1, 13):
            p = s_dir / f"amostra_{i}.jpg"
            if p.exists() and p.stat().st_size > 0:
                samples.append({
                    "index": i,
                    "path": p,
                    "label": f"Foto {i}",
                    "selected": (i == selected_idx),
                })

    if not samples and store is not None and hasattr(store, "profile_photos"):
        try:
            db_photos = store.profile_photos(child_id)
            for idx, (photo_id, jpeg_bytes, selected) in enumerate(db_photos, start=1):
                samples.append({
                    "index": idx,
                    "photo_id": photo_id,
                    "bytes": jpeg_bytes,
                    "label": f"Foto {idx}",
                    "selected": bool(selected or (idx == selected_idx)),
                })
        except Exception as e:
            logger.debug("Erro ao ler amostras do SQLite: %s", e)

    if not samples:
        curr = AVATAR_DIR / f"crianca_{child_id}.jpg"
        if curr.exists() and curr.stat().st_size > 0:
            samples.append({
                "index": 1,
                "path": curr,
                "label": "Foto Atual",
                "selected": True,
            })

    return samples


def select_child_sample_photo(
    child_id: int,
    sample_path_or_bytes,
    store=None,
    sample_index: Optional[int] = None,
    photo_id: Optional[int] = None,
) -> bool:
    """Aplica a amostra selecionada como a foto de perfil oficial da crianca."""
    try:
        ensure_avatar_dir()
        if isinstance(sample_path_or_bytes, (str, Path)):
            img = load_image_any_path(str(sample_path_or_bytes))
        elif isinstance(sample_path_or_bytes, bytes):
            arr = np.frombuffer(sample_path_or_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        else:
            return False

        if img is None or img.size == 0:
            return False

        jpg = AVATAR_DIR / f"crianca_{child_id}.jpg"
        cv2.imwrite(str(jpg), img)
        circle = generate_circular_png(img, 120)
        png = AVATAR_DIR / f"crianca_{child_id}_avatar.png"
        cv2.imwrite(str(png), circle)

        # Salva marcador do indice selecionado
        s_dir = AVATAR_DIR / f"amostras_{child_id}"
        if sample_index is not None:
            try:
                s_dir.mkdir(parents=True, exist_ok=True)
                (s_dir / "selecionada.txt").write_text(str(sample_index))
            except Exception:
                pass

        if store is not None:
            if sample_index is not None and hasattr(store, "set_setting"):
                try:
                    store.set_setting(f"selected_sample_{child_id}", str(sample_index))
                except Exception:
                    pass
            if photo_id is not None and hasattr(store, "select_profile_photo"):
                try:
                    store.select_profile_photo(child_id, photo_id)
                except Exception:
                    pass
            elif hasattr(store, "add_profile_photo"):
                try:
                    ok_enc, buf_enc = cv2.imencode(".jpg", img)
                    if ok_enc:
                        store.add_profile_photo(child_id, buf_enc.tobytes(), select=True)
                except Exception as e:
                    logger.debug("Erro ao atualizar profile_photo no SQLite: %s", e)

        logger.info("Foto de perfil da crianca %d atualizada com sucesso.", child_id)
        return True
    except Exception as e:
        logger.warning("Falha ao selecionar amostra da crianca %d: %s", child_id, e)
        return False
