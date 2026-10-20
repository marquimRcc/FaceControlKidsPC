"""Face Access Gate: OPT-IN webcam demonstration.

Local YuNet/SFace, read-only SQLite snapshot, in-memory timer. This NEVER
locks Windows or hides the desktop. ESC exits. No video is saved or uploaded.
"""
from __future__ import annotations

import argparse
import time
import tkinter as tk
from pathlib import Path
from queue import Empty
from tkinter import messagebox, ttk

from .gate_model import GateModel, GateState
from .webcam_observer import WebcamObserver, load_enrollments


BG = "#101b2e"
PANEL = "#1c2d46"
TEXT = "#f0f5fb"
MUTED = "#adc2d6"
AQUA = "#61d3b7"
WARNING = "#f0c071"

MESSAGES = {
    GateState.WAITING: ("Aguardando uma criança", "Aproxime-se da webcam."),
    GateState.VERIFYING: ("Identificando rosto", "Aguardando confirmação da identidade."),
    GateState.OPEN: ("Acesso visual autorizado", "A criança tem tempo disponível."),
    GateState.DENIED: ("Tempo esgotado", "Uma outra criança pode ser identificada."),
    GateState.UNKNOWN: ("Rosto desconhecido", "Nenhuma criança cadastrada reconhecida."),
    GateState.MULTIPLE: ("Mais de uma pessoa", "Mostre apenas um rosto para a webcam."),
    GateState.CAMERA_ERROR: ("Webcam indisponível", "Sem captura, o acesso visual não é liberado."),
    GateState.SERVICE_ERROR: ("Serviço indisponível", "Não há autorização disponível."),
}


def clock_label(seconds):
    sec = max(0, int(seconds))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Teste de liberação visual usando webcam local")
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--models", type=Path,
                        default=Path(__file__).resolve().parent.parent / "models")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--interval", type=float, default=2.0)
    return parser.parse_args(argv)


class LiveGate(tk.Tk):
    def __init__(self, profiles, worker):
        super().__init__()
        self.worker = worker
        self.model = GateModel(names=profiles.names)
        # These are copies, not a writable quota store.
        self.model.remaining = dict(profiles.balances)
        self.last_sample_at = time.monotonic()
        self.stale_limit = max(8.0, worker.interval * 3)
        self.configure(bg=BG)
        self.title("FaceControlKidsPC | Teste com webcam (sem bloquear o Windows)")
        self.geometry("880x665")
        self.minsize(650, 570)
        self.bind("<Escape>", lambda _: self.shutdown())
        self.protocol("WM_DELETE_WINDOW", self.shutdown)

        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=24, pady=(20, 16))
        self.label(header, "FaceControlKidsPC", 19, bold=True).pack(anchor="w")
        self.label(header, "WEBCAM LOCAL • DEMONSTRAÇÃO • NÃO BLOQUEIA O WINDOWS",
                   10, fg=WARNING).pack(anchor="w", pady=(5, 0))

        center = tk.Frame(self, bg=PANEL, padx=24, pady=23)
        center.pack(fill="both", expand=True, padx=24)
        self.state_text = tk.StringVar()
        self.detail_text = tk.StringVar()
        self.child_text = tk.StringVar()
        self.balance_text = tk.StringVar()
        self.note_text = tk.StringVar(value="Inicializando webcam local...")
        self.label(center, "◉", 47, fg=AQUA, bg=PANEL).pack(pady=(0, 8))
        self.label(center, "", 22, bold=True, bg=PANEL,
                   textvariable=self.state_text).pack(pady=4)
        self.label(center, "", 11, fg=MUTED, bg=PANEL,
                   textvariable=self.detail_text).pack(pady=4)
        self.label(center, "", 16, bold=True, bg=PANEL,
                   textvariable=self.child_text).pack(pady=(16, 3))
        self.label(center, "", 26, bold=True, fg=AQUA, bg=PANEL,
                   textvariable=self.balance_text).pack(pady=(0, 10))
        self.label(center, "", 10, bg=PANEL, fg=MUTED,
                   textvariable=self.note_text, wraplength=690).pack()

        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill="x", padx=24, pady=(16, 10))
        self.label(bottom, "Saldos: cópia local do início do teste; mudanças não são salvas.",
                   10, fg=MUTED).pack(anchor="w")
        self.balances = {}
        for pid, name in profiles.names.items():
            row = tk.Frame(bottom, bg=BG)
            row.pack(fill="x", pady=3)
            self.label(row, name, 11).pack(side="left")
            number = self.label(row, "", 11, fg=AQUA, bold=True)
            number.pack(side="right")
            self.balances[pid] = number

        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", padx=24, pady=(3, 20))
        self.label(footer, "Esc: sair • Sem vídeo gravado • Sem bloquear a sessão",
                   10, fg=MUTED).pack(side="left")
        ttk.Button(footer, text="Sair do teste", command=self.shutdown).pack(side="right")
        if profiles.unenrolled:
            self.note_text.set("Perfis sem amostras faciais: " + ", ".join(profiles.unenrolled))
        self._render()
        self.worker.start()
        self.after(250, self._poll)

    @staticmethod
    def label(container, text, size, *, fg=TEXT, bg=BG, bold=False, **kw):
        return tk.Label(container, text=text, fg=fg, bg=bg,
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kw)

    def _render(self):
        state = self.model.state
        title, desc = MESSAGES[state]
        if state is GateState.OPEN and self.model.absence_since is not None:
            desc = "Sem rosto: tempo pausado; restrição após 15 segundos de ausência."
        self.state_text.set(title)
        self.detail_text.set(desc)
        pid = self.model.active_child or self.model.last_child
        self.child_text.set(self.model.names[pid] if pid else "Ninguém autorizado")
        self.balance_text.set(clock_label(self.model.remaining[pid]) if pid else "--:--:--")
        for child, label in self.balances.items():
            label.configure(text=clock_label(self.model.remaining[child]),
                            fg=WARNING if self.model.remaining[child] <= 0 else AQUA)

    def _poll(self):
        if not self.winfo_exists():
            return
        now = time.monotonic()
        for _ in range(12):
            try:
                event, note = self.worker.events.get_nowait()
            except Empty:
                break
            self.last_sample_at = time.monotonic()
            self.model.observe(event, now)
            self.note_text.set(note)
        if time.monotonic() - self.last_sample_at > self.stale_limit:
            if self.model.state is not GateState.CAMERA_ERROR:
                self.model.observe("camera_error", now)
                self.note_text.set("Sem leituras recentes da câmera. Permissão visual suspensa.")
        self.model.advance(now)
        self._render()
        self.after(250, self._poll)

    def shutdown(self):
        self.worker.stop()
        self.destroy()


def main(argv=None):
    args = parse_args(argv)
    from .storage import default_data_path
    database = args.database or default_data_path()
    try:
        profiles = load_enrollments(database)
        for name in ("face_detection_yunet_2023mar.onnx",
                     "face_recognition_sface_2021dec.onnx"):
            if not (args.models / name).is_file():
                raise FileNotFoundError("Modelos ONNX não encontrados. Baixe pelo painel.")
        worker = WebcamObserver(args.models, profiles.embeddings,
                                camera_index=args.camera_index, interval=args.interval)
    except (OSError, ValueError, FileNotFoundError) as exc:
        root = tk.Tk()
        root.withdraw()
        try:
            messagebox.showerror("Teste de webcam", str(exc), parent=root)
        finally:
            root.destroy()
        raise SystemExit(2) from exc

    LiveGate(profiles, worker).mainloop()


if __name__ == "__main__":
    main()
