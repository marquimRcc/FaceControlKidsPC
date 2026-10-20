"""FaceControlKidsPC: safe windowed preview of the proposed face access gate.

IMPORTANT: NOT a Windows security lock. No camera, no disk writes, no services.
Only demo buttons synthesize observations; Esc and Exit always close the window.
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from .gate_model import GateModel, GateState


COLORS = {
    "bg": "#0c1424", "panel": "#142037", "side": "#f3f6fb",
    "white": "#f9fafb", "muted": "#9aaecb", "ink": "#1d2b3e",
    "teal": "#33cfaa", "amber": "#e8af52", "red": "#ef7979",
}

TITLES = {
    GateState.WAITING: ("Aguardando uma criança", "Aproxime-se da webcam para começar."),
    GateState.VERIFYING: ("Reconhecendo rosto…", "Confirmando a identidade observada."),
    GateState.OPEN: ("Uso autorizado", "A área de trabalho seria liberada."),
    GateState.DENIED: ("Tempo esgotado", "Esta criança já utilizou seu tempo diário."),
    GateState.UNKNOWN: ("Rosto não identificado", "Somente crianças cadastradas podem prosseguir."),
    GateState.MULTIPLE: ("Mais de um rosto", "Deixe apenas uma criança diante da câmera."),
    GateState.CAMERA_ERROR: ("Webcam indisponível", "A liberação permanece suspensa."),
    GateState.SERVICE_ERROR: ("Controlador indisponível", "A liberação permanece suspensa."),
}


def format_time(seconds: float) -> str:
    s = max(0, int(seconds))
    hours, rest = divmod(s, 3600)
    minutes, sec = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d}"


class GatePreview(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FaceControlKidsPC • Prova de conceito visual")
        self.geometry("1130x720")
        self.minsize(940, 590)
        self.configure(bg=COLORS["bg"])
        self.bind("<Escape>", lambda _: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.clock_offset = 0.0
        self.model = GateModel()
        self.pending_scan = 0
        self.status_note = "Nesta demonstração, os botões simulam observações da câmera."
        self.cards = {}
        self._build()
        self._refresh()
        self.after(250, self._tick)

    def _now(self):
        return time.monotonic() + self.clock_offset

    def _label(self, parent, text, *, fg=None, bg=None, size=12, bold=False, **options):
        return tk.Label(parent, text=text, fg=fg or COLORS["white"],
                        bg=bg or COLORS["panel"],
                        font=("Segoe UI", size, "bold" if bold else "normal"),
                        **options)

    def _build(self):
        header = tk.Frame(self, bg=COLORS["bg"])
        header.pack(fill="x", padx=25, pady=(18, 15))
        self._label(header, "FaceControlKidsPC", bg=COLORS["bg"], size=20,
                    bold=True).pack(side="left")
        self._label(header, "● SIMULAÇÃO — NÃO BLOQUEIA O WINDOWS",
                    bg=COLORS["bg"], fg=COLORS["amber"], size=10,
                    bold=True).pack(side="right")
        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=25, pady=(0, 14))

        left = tk.Frame(body, bg=COLORS["panel"], padx=30, pady=25)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))
        self._label(left, "TELA DE ACESSO FACIAL",
                    fg=COLORS["muted"], size=10).pack(anchor="w")

        stage = tk.Frame(left, bg=COLORS["panel"])
        stage.pack(expand=True, fill="both")
        camera = tk.Canvas(stage, bg=COLORS["panel"], highlightthickness=0, height=176)
        camera.pack(pady=(12, 4))
        cx, cy = 120, 82
        camera.create_oval(cx-75, cy-70, cx+75, cy+70, outline="#466a85", width=3)
        camera.create_oval(cx-30, cy-43, cx+30, cy+15, outline="#67b9c4", width=4)
        camera.create_arc(cx-52, cy+5, cx+52, cy+89, start=0, extent=180,
                          style="arc", outline="#67b9c4", width=4)
        camera.create_line(32, 150, 208, 150, fill="#446c7e", width=1)

        self.title_value = tk.StringVar()
        self.subtitle_value = tk.StringVar()
        self.state_value = tk.StringVar()
        self.child_value = tk.StringVar()
        self.remaining_value = tk.StringVar()
        self._label(stage, "", size=24, bold=True, textvariable=self.title_value,
                    wraplength=530).pack(pady=(0, 9))
        self._label(stage, "", fg=COLORS["muted"], size=12,
                    textvariable=self.subtitle_value, wraplength=530).pack(pady=(0, 18))
        self.status_badge = self._label(stage, "", size=10, bold=True,
                                        textvariable=self.state_value,
                                        padx=13, pady=9)
        self.status_badge.pack(pady=(0, 12))
        self._label(stage, "", size=15, bold=True,
                    textvariable=self.child_value).pack(pady=(0, 3))
        self._label(stage, "", fg=COLORS["teal"], size=28, bold=True,
                    textvariable=self.remaining_value).pack()
        self._label(left, "Esta janela representa um protótipo visual, não a área de trabalho real.",
                    size=9, fg=COLORS["muted"], wraplength=540).pack(anchor="w")

        right = tk.Frame(body, bg=COLORS["side"], padx=21, pady=19, width=395)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self._label(right, "Painel de demonstração", fg=COLORS["ink"],
                    bg=COLORS["side"], size=18, bold=True).pack(anchor="w")
        self._label(right, "Cada botão representa a leitura da webcam.",
                    fg="#64758c", bg=COLORS["side"], size=10).pack(anchor="w", pady=(2, 15))

        for child_id, name in self.model.names.items():
            card = tk.Frame(right, bg="#ffffff", padx=12, pady=10,
                            highlightthickness=1, highlightbackground="#dfe6f0")
            card.pack(fill="x", pady=4)
            top = tk.Frame(card, bg="white")
            top.pack(fill="x")
            self._label(top, name, fg=COLORS["ink"], bg="white",
                        size=12, bold=True).pack(side="left")
            balance = self._label(top, "", fg="#237b6a",
                                  bg="white", size=10, bold=True)
            balance.pack(side="right")
            bar = ttk.Progressbar(card, length=290, mode="determinate",
                                  maximum=7200)
            bar.pack(fill="x", pady=(8, 10))
            btn = ttk.Button(card, text="Simular reconhecimento",
                             command=lambda cid=child_id: self.select_child(cid))
            btn.pack(fill="x")
            self.cards[child_id] = (balance, bar, btn)

        events = tk.Frame(right, bg=COLORS["side"])
        events.pack(fill="x", pady=(12, 0))
        actions = [
            ("Sem rosto", lambda: self.event(None)),
            ("Desconhecido", lambda: self.event("unknown")),
            ("Dois rostos", lambda: self.event("multiple")),
            ("Erro na câmera", lambda: self.event("camera_error")),
            ("Erro no serviço", lambda: self.event("service_error")),
            ("Avançar 15 min", self.fast_forward),
        ]
        for index, (label, callback) in enumerate(actions):
            button = ttk.Button(events, text=label, command=callback)
            button.grid(row=index//2, column=index%2, padx=3, pady=4, sticky="ew")
        events.columnconfigure(0, weight=1)
        events.columnconfigure(1, weight=1)

        footer = tk.Frame(self, bg=COLORS["bg"])
        footer.pack(fill="x", padx=25, pady=(0, 18))
        self._label(footer, "ESC sai a qualquer momento • Sem webcam • Sem gravação de dados",
                    bg=COLORS["bg"], fg=COLORS["muted"], size=10).pack(side="left")
        ttk.Button(footer, text="Reiniciar teste",
                   command=self.reset).pack(side="right", padx=(6, 0))
        ttk.Button(footer, text="Sair da demonstração",
                   command=self.destroy).pack(side="right")

    def _invalidate_scan(self):
        self.pending_scan += 1
        return self.pending_scan

    def select_child(self, child_id: int):
        token = self._invalidate_scan()
        self.model.observe(child_id, self._now())
        self.status_note = "Primeira observação. Confirmando o mesmo rosto…"
        self._refresh()

        def second_sample():
            if token != self.pending_scan or not self.winfo_exists():
                return
            self.model.observe(child_id, self._now())
            self.status_note = "Identidade confirmada pelas duas amostras."
            self._refresh()

        self.after(850, second_sample)

    def event(self, observation):
        self._invalidate_scan()
        self.model.observe(observation, self._now())
        messages = {
            None: "Ausência detectada: cronômetro pausado; tolerância de 15 segundos.",
            "unknown": "Rosto não cadastrado: área de uso restrita.",
            "multiple": "Duas faces: identificação bloqueada por segurança.",
            "camera_error": "Simulando webcam indisponível.",
            "service_error": "Simulando falha na consulta do controlador."
        }
        self.status_note = messages[observation]
        self._refresh()

    def fast_forward(self):
        self._invalidate_scan()
        self.clock_offset += 15 * 60
        self.model.advance(self._now())
        self.status_note = "Relógio de demonstração avançou 15 minutos."
        self._refresh()

    def reset(self):
        self._invalidate_scan()
        self.clock_offset = 0.0
        self.model = GateModel()
        self.status_note = "Novo teste: saldos fictícios reiniciados."
        self._refresh()

    def _refresh(self):
        state = self.model.state
        title, subtitle = TITLES[state]
        if state is GateState.OPEN and self.model.absence_since is not None:
            subtitle = "Rosto ausente: aguardando retorno (tolerância de 15 segundos)."
        self.title_value.set(title)
        self.subtitle_value.set(subtitle)
        self.state_value.set("USO LIBERADO — APENAS SIMULAÇÃO" if state is GateState.OPEN
                             else "RESTRIÇÃO VISUAL — APENAS SIMULAÇÃO")
        self.status_badge.configure(fg=COLORS["teal"] if state is GateState.OPEN
                                    else COLORS["amber"])
        current = self.model.active_child or self.model.last_child
        self.child_value.set(self.model.names[current] if current else "Nenhuma criança ativa")
        self.remaining_value.set(format_time(self.model.remaining[current]) if current else "--:--:--")
        self.subtitle_value.set(subtitle + "\n" + self.status_note)
        for child_id, (balance, bar, _) in self.cards.items():
            seconds = self.model.remaining[child_id]
            balance.configure(text=format_time(seconds),
                              fg="#b34848" if seconds == 0 else "#237b6a")
            bar.configure(value=seconds)

    def _tick(self):
        if not self.winfo_exists():
            return
        self.model.advance(self._now())
        self._refresh()
        self.after(250, self._tick)


def main():
    app = GatePreview()
    app.mainloop()


if __name__ == "__main__":
    main()
