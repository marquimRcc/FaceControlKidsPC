"""Testes unitários do detector de vivacidade (Anti-Spoofing / Liveness)."""
import unittest
import numpy as np

from safepckids.liveness import PassiveLivenessDetector, LivenessDecision


class PassiveLivenessDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = PassiveLivenessDetector(
            min_samples=3,
            static_variance_threshold=0.00018,
            planar_ratio_variance_threshold=0.00008,
        )
        # Bounding box base: x=100, y=100, w=150, h=180
        # Landmarks: re=(130, 140), le=(190, 140), nt=(160, 170), rcm=(140, 220), lcm=(180, 220), score=0.95
        self.base_face = [
            100.0, 100.0, 150.0, 180.0,
            130.0, 140.0,
            190.0, 140.0,
            160.0, 170.0,
            140.0, 220.0,
            180.0, 220.0,
            0.95,
        ]

    def test_insufficient_frames_returns_negative(self):
        decision = self.detector.evaluate_sequence([self.base_face, self.base_face])
        self.assertFalse(decision.is_live)
        self.assertEqual(decision.reason, "INSUFFICIENT_FRAMES")

    def test_perfectly_static_photo_is_rejected(self):
        # 4 frames idênticos (foto estática na frente da webcam)
        frames = [list(self.base_face) for _ in range(4)]
        decision = self.detector.evaluate_sequence(frames)
        self.assertFalse(decision.is_live)
        self.assertEqual(decision.reason, "SPOOF_STATIC_IMAGE")
        self.assertGreaterEqual(decision.confidence, 0.90)

    def test_static_photo_with_subtle_sensor_noise_is_rejected(self):
        # Variação ínfima de ruído de sensor (< 0.00005)
        frames = []
        for i in range(4):
            f = list(self.base_face)
            f[4] += (i * 0.05)  # micro jitter irrisório
            f[6] += (i * 0.05)
            frames.append(f)
        decision = self.detector.evaluate_sequence(frames)
        self.assertFalse(decision.is_live)
        self.assertIn("SPOOF", decision.reason)

    def test_rigid_planar_motion_is_rejected(self):
        # Foto movida na mão: a caixa muda de posição x,y, mas os landmarks relativos são idênticos
        frames = []
        for i in range(5):
            f = list(self.base_face)
            f[0] += (i * 10.0)  # Move caixa em X
            f[1] += (i * 5.0)   # Move caixa em Y
            # Landmarks acompanham rigidamente em 2D
            for j in range(4, 14, 2):
                f[j] += (i * 10.0)
                f[j + 1] += (i * 5.0)
            frames.append(f)
        decision = self.detector.evaluate_sequence(frames)
        self.assertFalse(decision.is_live)
        self.assertIn("SPOOF", decision.reason)

    def test_live_human_micro_dynamics_is_confirmed(self):
        # Rosto humano real: respiração + micro-oscilações fisiológicas naturais
        frames = []
        rng = np.random.RandomState(42)
        for i in range(4):
            f = list(self.base_face)
            # Micro-ajuste fisiológico natural nas proporções dos olhos e boca (1 a 3 pixels)
            f[4] += float(rng.uniform(-1.5, 1.5))
            f[5] += float(rng.uniform(-0.8, 0.8))
            f[6] += float(rng.uniform(-1.5, 1.5))
            f[7] += float(rng.uniform(-0.8, 0.8))
            f[8] += float(rng.uniform(-1.0, 1.0))
            f[9] += float(rng.uniform(-1.2, 1.2))
            f[10] += float(rng.uniform(-1.0, 1.0))
            f[12] += float(rng.uniform(-1.0, 1.0))
            frames.append(f)

        decision = self.detector.evaluate_sequence(frames)
        self.assertTrue(decision.is_live)
        self.assertEqual(decision.reason, "LIVENESS_CONFIRMED")
        self.assertGreaterEqual(decision.confidence, 0.70)

    def test_corrupted_or_nan_landmarks_handled_safely(self):
        corrupted = list(self.base_face)
        corrupted[4] = float("nan")
        decision = self.detector.evaluate_sequence([corrupted, corrupted, corrupted])
        self.assertFalse(decision.is_live)
        self.assertEqual(decision.reason, "INSUFFICIENT_VALID_LANDMARKS")


if __name__ == "__main__":
    unittest.main()
