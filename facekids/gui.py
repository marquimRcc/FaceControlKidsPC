"""Painel parental experimental. Não aciona bloqueio real do Windows."""
from __future__ import annotations
import os
import sqlite3
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, simpledialog, messagebox

from .admin_auth import AUTH_SETTING, hash_pin, verify_pin
from .dashboard import cards_from_storage, time_label
from .storage import Storage

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"


def python_for_console():
    exe = Path(sys.executable)
    if os.name == "nt" and exe.name.lower() == "pythonw.exe":
        console = exe.with_name("python.exe")
        if console.exists():
            return str(console)
    return str(exe)


class ParentPanel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title("FaceControlKidsPC — Painel dos pais")
        self.geometry("930x650")
        self.minsize(750, 500)
        self.configure(background="#f5f7fb")
        self.db = Storage()
        self.process = None
        self.task = None
        self.protocol("WM_DELETE_WINDOW", self.exit)
        self.setup_style()
        self.layout()
        if not self.authenticate():
            self.db.close()
            self.destroy()
            return
        self.deiconify()
        self.refresh()
        self.after(3000, self.tick)

    def setup_style(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background="#f5f7fb")
        style.configure("TLabel", background="#f5f7fb",
                        foreground="#26374f", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Note.TLabel", foreground="#607186", font=("Segoe UI", 9))
        style.configure("TButton", padding=(12, 7))
        style.configure("Accent.TButton", background="#285dd1", foreground="white")
        style.configure("Card.TLabelframe", background="white", padding=12)
        style.configure("Card.TLabelframe.Label", font=("Segoe UI", 12, "bold"))

    def authenticate(self):
        stored = self.db.get_setting(AUTH_SETTING)
        if stored is None:
            messagebox.showinfo("Configuração inicial",
                 "Crie um PIN de 4 a 12 dígitos para o painel dos pais.\n"
                 "Ele protege apenas a interface, não o banco SQLite.", parent=self)
            pin = simpledialog.askstring("Criar PIN", "Defina o PIN:", show="*", parent=self)
            if pin is None:
                return False
            confirm = simpledialog.askstring("Confirmar PIN", "Repita o PIN:", show="*", parent=self)
            if confirm is None:
                return False
            if pin != confirm:
                messagebox.showerror("PIN", "Os dois PINs são diferentes.", parent=self)
                return False
            try:
                self.db.set_setting(AUTH_SETTING, hash_pin(pin))
            except ValueError as error:
                messagebox.showerror("PIN", str(error), parent=self)
                return False
            return True
        for attempt in range(3):
            pin = simpledialog.askstring("Acesso dos pais", "Informe seu PIN:", show="*", parent=self)
            if pin is None:
                return False
            if verify_pin(pin, stored):
                return True
            messagebox.showwarning("PIN incorreto", f"Tentativa {attempt + 1} de 3.", parent=self)
        return False

    def layout(self):
        outer = ttk.Frame(self, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="FaceControlKidsPC", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Controle de tempo por criança na conta compartilhada Filhos",
                  style="Note.TLabel").pack(anchor="w", pady=(0, 15))
        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x", pady=(0, 8))
        self.add_btn = ttk.Button(toolbar, text="+ Cadastrar criança",
                                  command=self.add_child, style="Accent.TButton")
        self.models_btn = ttk.Button(toolbar, text="Baixar modelos", command=self.download_models)
        self.monitor_btn = ttk.Button(toolbar, text="Iniciar simulação", command=self.monitor)
        self.stop_btn = ttk.Button(toolbar, text="Parar", command=self.stop)
        for btn in (self.add_btn, self.models_btn, self.monitor_btn, self.stop_btn):
            btn.pack(side="left", padx=(0, 8))
        self.status = tk.StringVar(value="Pronto")
        ttk.Label(outer, textvariable=self.status, style="Note.TLabel").pack(anchor="w", pady=(0, 8))

        scroll_frame = ttk.Frame(outer)
        scroll_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(scroll_frame, bg="#f5f7fb", highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.card_container = ttk.Frame(canvas)
        window_id = canvas.create_window(0, 0, window=self.card_container, anchor="nw")
        self.card_container.bind("<Configure>",
                                 lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda evt: canvas.itemconfigure(window_id, width=evt.width))
        ttk.Separator(outer).pack(fill="x", pady=(12, 8))
        ttk.Label(outer, text="MVP 0.3: simulação segura; bloqueio real desligado na interface.",
                  style="Note.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Cadastre e monitore sempre na mesma conta Windows (Filhos).",
                  style="Note.TLabel").pack(anchor="w")

    def busy(self):
        return self.process is not None and self.process.poll() is None

    def can_edit(self):
        if self.busy():
            messagebox.showinfo("Processo ativo", "Pare o monitoramento ou cadastro atual primeiro.", parent=self)
            return False
        return True

    def refresh(self):
        for child in self.card_container.winfo_children():
            child.destroy()
        cards = cards_from_storage(self.db)
        if not cards:
            ttk.Label(self.card_container,
                      text="Nenhuma criança cadastrada. Clique em '+ Cadastrar criança'.").pack(pady=24)
        for c in cards:
            frame = ttk.LabelFrame(self.card_container, text=c.name, style="Card.TLabelframe")
            frame.pack(fill="x", padx=7, pady=7)
            ttk.Label(frame, text=f"Tempo restante: {time_label(c.remaining_seconds)}").pack(anchor="w")
            ttk.Label(frame, text=f"Utilizado: {time_label(c.used_seconds)}  |  "
                      f"Limite: {c.limit_minutes}min  |  Bônus hoje: {c.bonus_minutes}min  |  "
                      f"Amostras faciais: {c.samples}").pack(anchor="w", pady=(5, 9))
            bar = ttk.Progressbar(frame, maximum=max(1, (c.limit_minutes + c.bonus_minutes)*60),
                                  value=min(c.used_seconds,(c.limit_minutes+c.bonus_minutes)*60))
            bar.pack(fill="x", pady=(0, 10))
            row = ttk.Frame(frame)
            row.pack(anchor="w")
            actions = (("Alterar limite", lambda child=c: self.change_limit(child)),
                       ("+15min hoje", lambda child=c: self.bonus(child)),
                       ("Cadastrar rosto", lambda child=c: self.enroll(child)))
            for text, callback in actions:
                button = ttk.Button(row, text=text, command=callback)
                button.configure(state="disabled" if self.busy() else "normal")
                button.pack(side="left", padx=(0, 8))
        for btn in (self.add_btn, self.models_btn, self.monitor_btn):
            btn.configure(state="disabled" if self.busy() else "normal")
        self.stop_btn.configure(state="normal" if self.busy() else "disabled")
        self.status.set(f"Executando: {self.task}" if self.busy() else
                        "Pronto • dados locais • bloqueio real desligado")

    def add_child(self):
        if not self.can_edit(): return
        name = simpledialog.askstring("Cadastro", "Nome ou apelido:", parent=self)
        if name is None: return
        minutes = simpledialog.askinteger("Limite", "Minutos diários (ex.: 120):",
                    initialvalue=120, minvalue=1, maxvalue=1440, parent=self)
        if minutes is None: return
        try:
            self.db.add_person(name, minutes)
            self.refresh()
        except (ValueError, sqlite3.IntegrityError) as error:
            messagebox.showerror("Cadastro", str(error), parent=self)

    def change_limit(self, child):
        if not self.can_edit(): return
        minutes = simpledialog.askinteger("Alterar limite",
                   f"Novo limite diário para {child.name} (em minutos):",
                   initialvalue=child.limit_minutes, minvalue=1, maxvalue=1440, parent=self)
        if minutes is not None:
            self.db.set_daily_limit(child.id, minutes)
            self.refresh()

    def bonus(self, child):
        if not self.can_edit(): return
        if messagebox.askyesno("Bônus", f"Conceder 15 minutos hoje para {child.name}?", parent=self):
            self.db.add_bonus(child.id, 15)
            self.refresh()

    def start(self, task, *args):
        if not self.can_edit(): return
        command = [python_for_console(), "-m", "facekids.cli",
                   "--database", str(self.db.path), "--models", str(MODELS), *map(str, args)]
        flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(command, cwd=ROOT, creationflags=flags)
            self.task = task
            self.refresh()
        except OSError as error:
            messagebox.showerror("Execução", str(error), parent=self)

    def download_models(self):
        if messagebox.askyesno("Modelos", "Baixar YuNet e SFace (~37 MB) do GitHub CrySence?", parent=self):
            self.start("Baixando modelos", "download-models")

    def enroll(self, child):
        if not self.can_edit(): return
        if not messagebox.askokcancel("Webcam", f"Mostre somente o rosto de {child.name}.\n"
               "Pressione Q na janela de vídeo para cancelar.", parent=self):
            return
        self.start("Cadastrando rosto", "enroll", child.name, "--samples", 20)

    def monitor(self):
        if not self.can_edit(): return
        if not self.db.people() or not self.db.embeddings():
            messagebox.showwarning("Cadastro incompleto",
                                   "Cadastre pelo menos uma criança e seu rosto.", parent=self)
            return
        if messagebox.askokcancel("Simulação segura",
                                  "Iniciar webcam e cronômetros sem bloquear o Windows?",
                                  parent=self):
            self.start("Simulação", "monitor", "--interval", 5)

    def stop(self):
        if not self.busy(): return
        if not messagebox.askyesno("Parar", "Interromper processo atual?", parent=self): return
        self.process.terminate()
        try: self.process.wait(timeout=3)
        except subprocess.TimeoutExpired: self.process.kill()
        self.process = None
        self.task = None
        self.refresh()

    def tick(self):
        if not self.winfo_exists(): return
        if self.process is not None and self.process.poll() is not None:
            code, task = self.process.returncode, self.task
            self.process = None
            self.task = None
            if code != 0:
                messagebox.showwarning("Processo encerrado",
                    f"{task} terminou com erro (código {code}). Confira a janela do console.",
                    parent=self)
        self.refresh()
        self.after(3000, self.tick)

    def exit(self):
        if self.busy():
            if not messagebox.askyesno("Sair", "Parar processo ativo e fechar o painel?", parent=self):
                return
            self.process.terminate()
            try: self.process.wait(timeout=3)
            except subprocess.TimeoutExpired: self.process.kill()
        self.db.close()
        self.destroy()


def main():
    app = ParentPanel()
    app.mainloop()

if __name__ == "__main__":
    main()
