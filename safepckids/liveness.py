"""Módulo de Verificação de Vivacidade (Liveness / Anti-Spoofing) Passivo.

Analisa a dinâmica temporal e perspectiva geométrica dos 5 marcos faciais
(landmarks) do detector YuNet ao longo de frames consecutivos para diferenciar
um rosto humano vivo de uma fotografia estática (papel ou tela de celular).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence
import numpy as np


@dataclass(frozen=True)
class LivenessDecision:
    is_live: bool
    reason: str
    confidence: float
    variance_landmarks: float
    variance_depth_ratio: float


class PassiveLivenessDetector:
    """Classificador de vivacidade passivo baseado na geometria temporal de landmarks.
    
    Invariantes e salvaguardas:
    1. Fotos estáticas em papel ou tela de celular possuem dispersão espacial inter-frame
       praticamente nula (variância < limiar estático).
    2. Fotos movidas manualmente possuem variação na posição global (x, y), mas a razão
       de profundidade projetada 3D (nariz x olhos x boca) permanece planarmente rígida.
    3. Seres humanos vivos exibem micro-oscilações fisiológicas (respiração, piscar,
       micro-expressões) gerando variância orgânica natural.
    """

    def __init__(
        self,
        min_samples: int = 2,
        static_variance_threshold: float = 0.00018,
        planar_ratio_variance_threshold: float = 0.00008,
    ):
        self.min_samples = max(2, int(min_samples))
        self.static_variance_threshold = float(static_variance_threshold)
        self.planar_ratio_variance_threshold = float(planar_ratio_variance_threshold)

    @staticmethod
    def extract_normalized_landmarks(face_box: Sequence[float]) -> Optional[np.ndarray]:
        """Extrai os 5 landmarks normalizados em relação à caixa facial (w, h)."""
        if face_box is None or len(face_box) < 14:
            return None

        try:
            x, y, w, h = float(face_box[0]), float(face_box[1]), float(face_box[2]), float(face_box[3])
        except (ValueError, TypeError, IndexError):
            return None

        if not np.isfinite(x) or not np.isfinite(y) or not np.isfinite(w) or not np.isfinite(h):
            return None
        if w <= 1.0 or h <= 1.0:
            return None

        # Landmarks: [re_x, re_y, le_x, le_y, nt_x, nt_y, rcm_x, rcm_y, lcm_x, lcm_y]
        raw_pts = []
        for i in range(4, 14, 2):
            px = float(face_box[i])
            py = float(face_box[i + 1])
            if not np.isfinite(px) or not np.isfinite(py):
                return None
            norm_x = (px - x) / w
            norm_y = (py - y) / h
            raw_pts.extend([norm_x, norm_y])

        return np.asarray(raw_pts, dtype=np.float32)

    @classmethod
    def compute_perspective_ratio(cls, norm_pts: np.ndarray) -> float:
        """Calcula a razão de perspectiva geométrica entre os olhos e o triângulo nasal-bucal."""
        re_x, re_y = norm_pts[0], norm_pts[1]
        le_x, le_y = norm_pts[2], norm_pts[3]
        nt_x, nt_y = norm_pts[4], norm_pts[5]
        rcm_x, rcm_y = norm_pts[6], norm_pts[7]
        lcm_x, lcm_y = norm_pts[8], norm_pts[9]

        inter_eye_dist = np.hypot(le_x - re_x, le_y - re_y)
        mouth_center_x = (rcm_x + lcm_x) * 0.5
        mouth_center_y = (rcm_y + lcm_y) * 0.5
        eye_mouth_dist = np.hypot(mouth_center_x - (re_x + le_x) * 0.5, mouth_center_y - (re_y + le_y) * 0.5)

        if eye_mouth_dist <= 1e-6:
            return 1.0

        return float(inter_eye_dist / eye_mouth_dist)

    def can_evaluate(self, face_boxes: Sequence[Sequence[float]]) -> bool:
        """Retorna True se houver quantidade suficiente de caixas faciais com marcos (landmarks) para avaliação."""
        if not face_boxes or len(face_boxes) < self.min_samples:
            return False
        valid = 0
        for b in face_boxes:
            if b is not None and len(b) >= 14:
                valid += 1
        return valid >= self.min_samples

    def evaluate_sequence(self, face_boxes: Sequence[Sequence[float]]) -> LivenessDecision:
        """Avalia uma sequência temporal de caixas faciais detectadas para o mesmo candidato."""
        if not face_boxes or len(face_boxes) < self.min_samples:
            return LivenessDecision(
                is_live=False,
                reason="INSUFFICIENT_FRAMES",
                confidence=0.0,
                variance_landmarks=0.0,
                variance_depth_ratio=0.0,
            )

        extracted_landmarks: List[np.ndarray] = []
        perspective_ratios: List[float] = []

        for box in face_boxes:
            pts = self.extract_normalized_landmarks(box)
            if pts is not None:
                extracted_landmarks.append(pts)
                perspective_ratios.append(self.compute_perspective_ratio(pts))

        if len(extracted_landmarks) < self.min_samples:
            return LivenessDecision(
                is_live=False,
                reason="INSUFFICIENT_VALID_LANDMARKS",
                confidence=0.0,
                variance_landmarks=0.0,
                variance_depth_ratio=0.0,
            )

        matrix = np.vstack(extracted_landmarks)  # Shape: (N, 10)
        # Variância média por coordenada dos marcos normalizados
        landmark_variance = float(np.mean(np.var(matrix, axis=0)))
        # Variância da razão de perspectiva 3D
        ratio_variance = float(np.var(perspective_ratios))

        # Caso 1: Foto estática / congelamento artificial
        if landmark_variance < self.static_variance_threshold and ratio_variance < self.planar_ratio_variance_threshold:
            return LivenessDecision(
                is_live=False,
                reason="SPOOF_STATIC_IMAGE",
                confidence=0.95,
                variance_landmarks=landmark_variance,
                variance_depth_ratio=ratio_variance,
            )

        # Caso 2: Foto em movimento planar rígido (movida com a mão diante da lente)
        if ratio_variance < (self.planar_ratio_variance_threshold * 0.5):
            return LivenessDecision(
                is_live=False,
                reason="SPOOF_RIGID_PLANAR_MOTION",
                confidence=0.90,
                variance_landmarks=landmark_variance,
                variance_depth_ratio=ratio_variance,
            )

        # Caso 3: Vivacidade humana orgânica confirmada
        confidence = min(0.99, max(0.70, float(1.0 - (self.static_variance_threshold / (landmark_variance + 1e-7)))))
        return LivenessDecision(
            is_live=True,
            reason="LIVENESS_CONFIRMED",
            confidence=confidence,
            variance_landmarks=landmark_variance,
            variance_depth_ratio=ratio_variance,
        )
