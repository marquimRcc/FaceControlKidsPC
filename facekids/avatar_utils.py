"""Utilitários para processamento e corte de fotos de avatar das crianças."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("FaceKidsAvatar")
AVATAR_DIR = Path("C:/ProgramData/FaceKids/fotos")


def ensure_avatar_dir() -> Path:
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    return AVATAR_DIR


def save_child_photo(child_id: int, frame: np.ndarray, face_box: Optional[list | np.ndarray] = None) -> Optional[Path]:
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


def get_child_avatar_path(child_id: int) -> Optional[Path]:
    """Retorna o caminho do PNG circular da crianca, ou o JPEG original se nao existir o PNG."""
    png = AVATAR_DIR / f"crianca_{child_id}_avatar.png"
    if png.exists():
        return png
    jpg = AVATAR_DIR / f"crianca_{child_id}.jpg"
    if jpg.exists():
        return jpg
    return None
