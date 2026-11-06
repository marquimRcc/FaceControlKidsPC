"""FaceControlKidsPC - Servico de Camera e Transmissao MJPEG em Tempo Real.

Gerencia o ciclo de vida da webcam, deteccao facial com YuNet e
cadastro biometrico de 12 amostras integrado diretamente a interface web.
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Dict, Generator, List, Optional, Tuple

import cv2
import numpy as np

from .avatar_utils import save_child_photo, get_child_samples_dir
from .parent_face_pilot import REQUIRED_SAMPLES, _valid_features, replace_templates
from .recognition import Recognizer
from .storage import Storage


logger = logging.getLogger("facekids.camera_service")

def get_models_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS) / "models"
        if p.exists():
            return p
    return Path(__file__).resolve().parent.parent / "models"

MODELS_DIR = get_models_dir()


class CameraService:
    _instance: Optional[CameraService] = None
    _lock = threading.Lock()

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self._cap: Optional[cv2.VideoCapture] = None
        self._recognizer: Optional[Recognizer] = None
        self._streaming_clients = 0
        self._cam_lock = threading.Lock()
        
        # Estado do cadastro biometrico em andamento
        self.enrollment_state: Dict[str, Any] = {
            "active": False,
            "child_id": 0,
            "samples_count": 0,
            "total_required": REQUIRED_SAMPLES,
            "completed": False,
            "error": None,
            "message": "Pronto para iniciar.",
            "latest_avatar_b64": None
        }

    @classmethod
    def get_instance(cls) -> CameraService:
        with cls._lock:
            if cls._instance is None:
                cls._instance = CameraService()
            return cls._instance

    @property
    def recognizer(self) -> Recognizer:
        if self._recognizer is None:
            self._recognizer = Recognizer(MODELS_DIR)
        return self._recognizer

    def _open_device(self) -> bool:
        if self._cap is not None and self._cap.isOpened():
            return True

        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF] if sys.platform == "win32" else [cv2.CAP_ANY]
        for b in backends:
            try:
                cap = cv2.VideoCapture(self.camera_index, b)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    self._cap = cap
                    logger.info("Camera aberta com sucesso no backend %s", b)
                    return True
                cap.release()
            except Exception as e:
                logger.warning("Erro ao tentar abrir camera no backend %s: %s", b, e)

        return False

    def _close_device(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
            logger.info("Camera liberada.")

    def get_latest_frame(self, draw_overlay: bool = True) -> Tuple[bool, Optional[np.ndarray], List[Any]]:
        with self._cam_lock:
            if not self._open_device():
                return False, None, []

            ret, frame = self._cap.read()
            if not ret or frame is None:
                return False, None, []

            clean_frame = frame.copy()
            faces = []
            try:
                faces = self.recognizer.faces(clean_frame)
            except Exception as e:
                logger.debug("Aviso na deteccao facial: %s", e)

            if draw_overlay:
                overlay_frame = frame.copy()
                H, W = overlay_frame.shape[:2]
                
                if len(faces) == 1:
                    fx, fy, fw, fh = int(faces[0][0]), int(faces[0][1]), int(faces[0][2]), int(faces[0][3])
                    # Caixa retangular elegante com cantos destacados (Ciano #06b6d4 -> BGR: 212, 182, 6)
                    cv2.rectangle(overlay_frame, (fx, fy), (fx + fw, fy + fh), (212, 182, 6), 2, cv2.LINE_AA)
                    
                    # Desenha cantos estilizados
                    line_len = min(fw, fh) // 5
                    # Canto superior esquerdo
                    cv2.line(overlay_frame, (fx, fy), (fx + line_len, fy), (255, 230, 80), 4)
                    cv2.line(overlay_frame, (fx, fy), (fx, fy + line_len), (255, 230, 80), 4)
                    # Canto superior direito
                    cv2.line(overlay_frame, (fx + fw, fy), (fx + fw - line_len, fy), (255, 230, 80), 4)
                    cv2.line(overlay_frame, (fx + fw, fy), (fx + fw, fy + line_len), (255, 230, 80), 4)
                    # Canto inferior esquerdo
                    cv2.line(overlay_frame, (fx, fy + fh), (fx + line_len, fy + fh), (255, 230, 80), 4)
                    cv2.line(overlay_frame, (fx, fy + fh), (fx, fy + fh - line_len), (255, 230, 80), 4)
                    # Canto inferior direito
                    cv2.line(overlay_frame, (fx + fw, fy + fh), (fx + fw - line_len, fy + fh), (255, 230, 80), 4)
                    cv2.line(overlay_frame, (fx + fw, fy + fh), (fx + fw, fy + fh - line_len), (255, 230, 80), 4)

                    label = "ROSTO DETECTADO (IA OK)"
                    cv2.putText(overlay_frame, label, (fx, max(24, fy - 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (212, 182, 6), 2, cv2.LINE_AA)
                elif len(faces) > 1:
                    cv2.putText(overlay_frame, "ATENCAO: Apenas 1 pessoa por vez", (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (50, 50, 240), 2, cv2.LINE_AA)
                else:
                    # Guia circular sutil no centro
                    cv2.circle(overlay_frame, (W // 2, H // 2), H // 3, (80, 80, 80), 1, cv2.LINE_AA)
                    cv2.putText(overlay_frame, "Olhe para a webcam...", (W // 2 - 100, H - 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1, cv2.LINE_AA)

                return True, overlay_frame, faces

            return True, clean_frame, faces

    def generate_mjpeg_stream(self) -> Generator[bytes, None, None]:
        """Gera um fluxo continuo de quadros multipart/x-mixed-replace (MJPEG)."""
        with self._cam_lock:
            self._streaming_clients += 1

        try:
            while True:
                ok, frame, _ = self.get_latest_frame(draw_overlay=True)
                if not ok or frame is None:
                    # Gera um quadro simulado placeholder se a camera fisica nao abrir
                    placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(placeholder, "Conectando a camera...", (180, 240),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
                    _, buf = cv2.imencode(".jpg", placeholder, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    frame_bytes = buf.tobytes()
                else:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    frame_bytes = buf.tobytes()

                chunk = (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame_bytes)).encode("ascii") + b"\r\n\r\n"
                    + frame_bytes + b"\r\n"
                )
                yield chunk
                time.sleep(0.04)  # ~25 FPS
        finally:
            with self._cam_lock:
                self._streaming_clients = max(0, self._streaming_clients - 1)
                if self._streaming_clients == 0 and not self.enrollment_state["active"]:
                    self._close_device()

    def start_enrollment(self, child_id: int, db_path: Path) -> Dict[str, Any]:
        """Inicia o processo de captura de 12 fotos em thread dedicada."""
        if self.enrollment_state["active"]:
            return {"ok": False, "error": "Um cadastro ja esta em andamento."}

        self.enrollment_state = {
            "active": True,
            "child_id": child_id,
            "samples_count": 0,
            "total_required": REQUIRED_SAMPLES,
            "completed": False,
            "error": None,
            "message": "Iniciando captura. Olhe para a webcam...",
            "latest_avatar_b64": None
        }

        thread = threading.Thread(
            target=self._run_enrollment_worker,
            args=(child_id, db_path),
            daemon=True
        )
        thread.start()
        return {"ok": True, "message": "Captura iniciada."}

    def _run_enrollment_worker(self, child_id: int, db_path: Path) -> None:
        vectors: List[np.ndarray] = []
        samples_crops: List[np.ndarray] = []
        best_face_frame = None
        best_face_box = None
        next_sample_time = time.monotonic()

        store = Storage(db_path)
        try:
            logger.info("Iniciando sessao de cadastro biometrico para crianca ID %d", child_id)
            while len(vectors) < REQUIRED_SAMPLES and self.enrollment_state["active"]:
                ok, clean_frame, faces = self.get_latest_frame(draw_overlay=False)
                if not ok or clean_frame is None:
                    time.sleep(0.1)
                    continue

                now = time.monotonic()
                if len(faces) == 1:
                    fx, fy, fw, fh = int(faces[0][0]), int(faces[0][1]), int(faces[0][2]), int(faces[0][3])
                    
                    if now >= next_sample_time:
                        try:
                            vector = self.recognizer.features(clean_frame, faces[0])
                            if _valid_features(vector):
                                vectors.append(np.asarray(vector, dtype=np.float32).reshape(128).copy())
                                
                                H, W = clean_frame.shape[:2]
                                mx, my = int(fw * 0.30), int(fh * 0.30)
                                x1, y1 = max(0, fx - mx), max(0, fy - my)
                                x2, y2 = min(W, fx + fw + mx), min(H, fy + fh + my)
                                crop = clean_frame[y1:y2, x1:x2].copy()
                                samples_crops.append(crop)
                                
                                best_face_frame = clean_frame.copy()
                                best_face_box = faces[0]
                                
                                self.enrollment_state["samples_count"] = len(vectors)
                                self.enrollment_state["message"] = f"Amostra {len(vectors)} de {REQUIRED_SAMPLES} capturada..."
                                
                                # Intervalo de 0.4s entre amostras para variar angulo
                                next_sample_time = now + 0.40
                        except Exception as e:
                            logger.debug("Erro ao extrair caracteristicas faciais: %s", e)
                elif len(faces) > 1:
                    self.enrollment_state["message"] = "Multiplos rostos visiveis. Apenas a crianca deve olhar para a camera."
                else:
                    self.enrollment_state["message"] = "Posicione o rosto no centro da camera..."

                time.sleep(0.04)

            if len(vectors) >= REQUIRED_SAMPLES:
                # 1. Salva vetores no banco
                replace_templates(store, child_id, vectors)

                # 2. Salva fotos cortadas
                samples_dir = get_child_samples_dir(child_id)
                samples_dir.mkdir(parents=True, exist_ok=True)
                for old_f in samples_dir.glob("amostra_*.jpg"):
                    try:
                        old_f.unlink()
                    except Exception:
                        pass

                if hasattr(store, "clear_profile_photos"):
                    store.clear_profile_photos(child_id)

                for i, sample_crop in enumerate(samples_crops, start=1):
                    sample_p = samples_dir / f"amostra_{i}.jpg"
                    cv2.imwrite(str(sample_p), sample_crop)
                    try:
                        ok_enc, buf_enc = cv2.imencode(".jpg", sample_crop)
                        if ok_enc and hasattr(store, "add_profile_photo"):
                            store.add_profile_photo(child_id, buf_enc.tobytes(), select=(i == 1))
                    except Exception:
                        pass

                if best_face_frame is not None:
                    save_child_photo(child_id, best_face_frame, best_face_box, store=store)

                # Gera versao Base64 do avatar final para exibir na tela imediatamente
                avatar_path = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "FaceKids" / "fotos" / f"crianca_{child_id}_avatar.png"
                if avatar_path.exists():
                    b64 = base64.b64encode(avatar_path.read_bytes()).decode("ascii")
                    self.enrollment_state["latest_avatar_b64"] = f"data:image/png;base64,{b64}"

                self.enrollment_state["completed"] = True
                self.enrollment_state["message"] = "Cadastro concluido com sucesso! 12 amostras salvas."
                logger.info("Cadastro biometrico concluido para crianca ID %d", child_id)
        except Exception as e:
            logger.error("Falha no worker de cadastro biometrico: %s", e)
            self.enrollment_state["error"] = str(e)
            self.enrollment_state["message"] = f"Erro no cadastro: {e}"
        finally:
            self.enrollment_state["active"] = False
            store.close()
            with self._cam_lock:
                if self._streaming_clients == 0:
                    self._close_device()
