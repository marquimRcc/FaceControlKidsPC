"""Reconhecimento local OpenCV YuNet/SFace (sem envio de imagem à internet)."""
from pathlib import Path
import numpy as np

DETECTOR_FILE = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_FILE = "face_recognition_sface_2021dec.onnx"

class Recognizer:
    def __init__(self, model_dir: Path):
        import cv2
        self.cv2 = cv2
        det = Path(model_dir)/DETECTOR_FILE
        rec = Path(model_dir)/RECOGNIZER_FILE
        if not det.is_file() or not rec.is_file():
            raise FileNotFoundError("Modelos ONNX ausentes: execute `python -m facekids.cli download-models`.")
        self.detector = cv2.FaceDetectorYN.create(str(det), "", (320,320), 0.7,0.3,5000)
        self.recognizer = cv2.FaceRecognizerSF.create(str(rec),"")

    def faces(self, frame):
        h,w = frame.shape[:2]
        self.detector.setInputSize((w,h))
        _,faces = self.detector.detect(frame)
        return [] if faces is None else list(faces)

    def features(self, frame,face):
        aligned = self.recognizer.alignCrop(frame,face)
        return np.asarray(self.recognizer.feature(aligned),dtype=np.float32).reshape(-1)

    @staticmethod
    def identify(vec: np.ndarray, reference: list[tuple[int,np.ndarray]], threshold=0.50, min_margin=0.07):
        """Compara 1:N; exige bom score e margem contra o segundo colocado."""
        v = np.asarray(vec,dtype=np.float32).reshape(-1)
        scores = {}
        for pid, ref in reference:
            r = np.asarray(ref,dtype=np.float32).reshape(-1)
            if r.shape != v.shape: continue
            denom = float(np.linalg.norm(v)*np.linalg.norm(r))
            if denom == 0: continue
            sim = float(np.dot(v,r)/denom)
            scores[pid] = max(scores.get(pid,-1.0),sim)
        ranked = sorted(scores.items(),key=lambda it:it[1],reverse=True)
        if not ranked or ranked[0][1] < threshold:
            return None, (ranked[0][1] if ranked else None)
        if len(ranked)>1 and ranked[0][1]-ranked[1][1] < min_margin:
            return None,ranked[0][1]
        return ranked[0]
