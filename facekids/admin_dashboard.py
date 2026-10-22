"""FaceControlKidsPC - Painel de Controle e Gerenciamento dos Pais.

Interface moderna, escura e completa exclusiva para a conta do Administrador (MarcosMiniPC):
- Visualizacao de todos os perfis de criancas (Filho 1, 2, 3...)
- Selecao/atualizacao de fotos a partir de arquivos do computador (.jpg, .png, etc.)
  com recorte automatico do rosto, geracao de avatar circular e extracao de biometria SFace
- Cadastro guiado via Webcam (12 amostras com feedback ao vivo)
- Alteracao de nomes dos filhos
- Ajuste de limites diarios de tempo (presets de 1h, 1h30, 2h, 3h ou personalizado)
- Concessao de bonus diario de tempo (+15m, +30m, +60m)
- Gerenciamento de programas a inicializar automaticamente apos o desbloqueio facial
- Protecao de acesso: execucao restrita a conta dos Pais (nunca na conta Filhos)
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from .avatar_utils import (
    AVATAR_DIR,
    get_child_avatar_path,
    remove_child_avatar_files,
    set_child_photo_from_file,
)
from .children_pilot import child_pilot_database, windows_token_user
from .platform_paths import application_data_dir
from .storage import Storage

logger = logging.getLogger("FaceKidsAdmin")

ROOT_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT_DIR / "models"
PROGRAMS_FILE = application_data_dir() / "programas_inicializar.json"

# Paleta Moderna Escura (Alinhada com Catppuccin Mocha / Welcome Screen)
BG_MAIN = "#0F0F17"
BG_HEADER = "#181825"
BG_CARD = "#181825"
BG_BOX = "#1E1E2E"
BG_BOX_HOVER = "#252538"
BORDER_DEFAULT = "#313244"
BORDER_ACCENT = "#38BDF8"

TEXT_TITLE = "#CDD6F4"
TEXT_SUB = "#A6ADC8"
TEXT_MUTED = "#6C7086"

ACCENT_BLUE = "#38BDF8"
ACCENT_CYAN = "#89DCEB"
ACCENT_GREEN = "#A6E3A1"
ACCENT_YELLOW = "#F9E2AF"
ACCENT_RED = "#F38BA8"
ACCENT_PURPLE = "#CBA6F7"


def is_admin_account() -> bool:
    """Verifica se o usuario atual e o pai (MarcosMiniPC) e nao a conta Filhos."""
    try:
        user = windows_token_user()
        if user.casefold() == "filhos":
            return False
        return True
    except Exception:
        # Fallback para ambiente de desenvolvimento/teste
        return os.environ.get("USERNAME", "").casefold() != "filhos"


def time_format_hm(seconds: float | int) -> str:
    """Formata segundos em 'Xh Ymin' ou 'Y min'."""
    sec = max(0, int(seconds))
    hours, minutes = divmod(sec // 60, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}min"
    return f"{minutes} min"


class ProgramsConfigDialog(tk.Toplevel):
    """Janela modal para configurar programas de inicializacao automatica."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Configurar Programas de Inicialização")
        self.geometry("540x480")
        self.configure(bg=BG_MAIN)
        self.transient(parent)
        self.grab_set()

        self.config_data = self._load()
        self._build_ui()

    def _load(self) -> dict:
        default = {
            "enabled": True,
            "description": "Lista de programas a inicializar automaticamente apos o desbloqueio facial",
            "programs": [
                {
                    "name": "Brave - YouTube Kids",
                    "executable": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                    "arguments": "--new-window https://www.youtubekids.com",
                    "enabled": True,
                }
            ],
        }
        if PROGRAMS_FILE.exists():
            try:
                return json.loads(PROGRAMS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return default

    def _save(self):
        try:
            PROGRAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
            PROGRAMS_FILE.write_text(json.dumps(self.config_data, indent=2, ensure_ascii=False), encoding="utf-8")
            messagebox.showinfo("Sucesso", "Configuração salva com sucesso!", parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar configuração: {e}", parent=self)

    def _build_ui(self):
        pad = tk.Frame(self, bg=BG_MAIN, padx=16, pady=16)
        pad.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            pad,
            text="🚀 Programas de Inicialização Automática",
            font=("Segoe UI", 13, "bold"),
            fg=TEXT_TITLE,
            bg=BG_MAIN,
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            pad,
            text="Estes programas abrem automaticamente na conta Filhos após o desbloqueio facial.",
            font=("Segoe UI", 9),
            fg=TEXT_SUB,
            bg=BG_MAIN,
            wraplength=490,
            justify="left",
        ).pack(anchor="w", pady=(0, 14))

        # Checkbox Master
        self.master_var = tk.BooleanVar(value=self.config_data.get("enabled", False))
        cb = tk.Checkbutton(
            pad,
            text="Habilitar inicialização de programas ao desbloquear o PC",
            variable=self.master_var,
            command=self._on_master_toggle,
            font=("Segoe UI", 10, "bold"),
            fg=ACCENT_CYAN,
            bg=BG_MAIN,
            activeforeground=ACCENT_CYAN,
            activebackground=BG_MAIN,
            selectcolor=BG_BOX,
        )
        cb.pack(anchor="w", pady=(0, 12))

        # Lista de Programas
        list_frame = tk.Frame(pad, bg=BG_BOX, highlightbackground=BORDER_DEFAULT, highlightthickness=1)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 14))

        self.items_container = tk.Frame(list_frame, bg=BG_BOX, padx=10, pady=10)
        self.items_container.pack(fill=tk.BOTH, expand=True)

        self._refresh_programs_list()

        # Botoes de Acao
        btn_bar = tk.Frame(pad, bg=BG_MAIN)
        btn_bar.pack(fill=tk.X)

        add_btn = tk.Button(
            btn_bar,
            text="➕ Adicionar Programa",
            font=("Segoe UI", 9, "bold"),
            bg=BG_BOX,
            fg=ACCENT_BLUE,
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=5,
            command=self._add_program,
        )
        add_btn.pack(side=tk.LEFT)

        save_btn = tk.Button(
            btn_bar,
            text="💾 Salvar Alterações",
            font=("Segoe UI", 9, "bold"),
            bg=ACCENT_BLUE,
            fg="#0B0B12",
            relief=tk.FLAT,
            cursor="hand2",
            padx=14,
            pady=5,
            command=self._save,
        )
        save_btn.pack(side=tk.RIGHT)

    def _on_master_toggle(self):
        self.config_data["enabled"] = self.master_var.get()

    def _refresh_programs_list(self):
        for w in self.items_container.winfo_children():
            w.destroy()

        programs = self.config_data.get("programs", [])
        if not programs:
            tk.Label(
                self.items_container,
                text="Nenhum programa cadastrado.",
                font=("Segoe UI", 10),
                fg=TEXT_MUTED,
                bg=BG_BOX,
            ).pack(pady=20)
            return

        for idx, prog in enumerate(programs):
            row = tk.Frame(self.items_container, bg=BG_BOX)
            row.pack(fill=tk.X, pady=4)

            var = tk.BooleanVar(value=prog.get("enabled", False))

            def _toggle(p=prog, v=var):
                p["enabled"] = v.get()

            cb = tk.Checkbutton(
                row,
                variable=var,
                command=_toggle,
                bg=BG_BOX,
                selectcolor="#11111B",
                activebackground=BG_BOX,
            )
            cb.pack(side=tk.LEFT)

            info = tk.Label(
                row,
                text=f"{prog.get('name', 'Programa')} ({prog.get('executable', '')})",
                font=("Segoe UI", 9, "bold" if prog.get("enabled") else "normal"),
                fg=TEXT_TITLE if prog.get("enabled") else TEXT_MUTED,
                bg=BG_BOX,
            )
            info.pack(side=tk.LEFT, padx=4)

            def _del(index=idx):
                self.config_data["programs"].pop(index)
                self._refresh_programs_list()

            del_btn = tk.Button(
                row,
                text="✕",
                font=("Segoe UI", 8, "bold"),
                fg=ACCENT_RED,
                bg=BG_BOX,
                relief=tk.FLAT,
                cursor="hand2",
                command=_del,
            )
            del_btn.pack(side=tk.RIGHT)

    def _add_program(self):
        name = simpledialog.askstring("Novo Programa", "Nome amigável (ex: Navegador Edge, Minecraft):", parent=self)
        if not name:
            return
        exe = simpledialog.askstring("Executável", "Nome do executável ou comando (ex: msedge.exe, notepad.exe):", parent=self)
        if not exe:
            return
        args = simpledialog.askstring("Argumentos (opcional)", "Argumentos adicionais (ou deixe em branco):", parent=self) or ""

        self.config_data.setdefault("programs", []).append({
            "name": name.strip(),
            "executable": exe.strip(),
            "arguments": args.strip(),
            "enabled": True,
        })
        self._refresh_programs_list()


class WeeklyUsageDialog(tk.Toplevel):
    """Janela modal para visualizacao do historico de uso semanal dos filhos."""

    def __init__(self, parent, store: Storage):
        super().__init__(parent)
        self.title("Histórico de Uso dos Últimos 7 Dias")
        self.geometry("660x540")
        self.configure(bg=BG_MAIN)
        self.transient(parent)
        self.grab_set()
        self.store = store
        self._build_ui()

    def _build_ui(self):
        pad = tk.Frame(self, bg=BG_MAIN, padx=18, pady=16)
        pad.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            pad,
            text="📊 Histórico de Uso dos Últimos 7 Dias",
            font=("Segoe UI", 13, "bold"),
            fg=TEXT_TITLE,
            bg=BG_MAIN,
        ).pack(anchor="w", pady=(0, 4))

        tk.Label(
            pad,
            text="Acompanhe o tempo de tela utilizado por cada filho ao longo da semana.",
            font=("Segoe UI", 9),
            fg=TEXT_SUB,
            bg=BG_MAIN,
        ).pack(anchor="w", pady=(0, 14))

        canvas = tk.Canvas(pad, bg=BG_MAIN, highlightthickness=0)
        scrollbar = tk.Scrollbar(pad, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        container = tk.Frame(canvas, bg=BG_MAIN)
        win_id = canvas.create_window((0, 0), window=container, anchor="nw")
        container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        people = self.store.people()
        if not people:
            tk.Label(container, text="Nenhum perfil cadastrado.", font=("Segoe UI", 10), fg=TEXT_MUTED, bg=BG_MAIN).pack(pady=20)
            return

        for pid, name, _ in people:
            history = self.store.get_history(pid, 7)
            total_sec = sum(sec for _, sec in history)
            avg_sec = total_sec / max(1, len(history))

            card = tk.Frame(container, bg=BG_CARD, highlightbackground=BORDER_DEFAULT, highlightthickness=1, padx=14, pady=12)
            card.pack(fill=tk.X, pady=8)

            header = tk.Frame(card, bg=BG_CARD)
            header.pack(fill=tk.X, pady=(0, 8))

            tk.Label(header, text=name, font=("Segoe UI", 12, "bold"), fg=ACCENT_BLUE, bg=BG_CARD).pack(side=tk.LEFT)
            tk.Label(header, text=f"Total: {time_format_hm(total_sec)}  |  Média: {time_format_hm(avg_sec)}/dia", font=("Segoe UI", 9, "bold"), fg=ACCENT_GREEN, bg=BG_CARD).pack(side=tk.RIGHT)

            for day_str, sec in reversed(history):
                row = tk.Frame(card, bg=BG_BOX, padx=8, pady=4, highlightbackground=BORDER_DEFAULT, highlightthickness=1)
                row.pack(fill=tk.X, pady=2)

                tk.Label(row, text=day_str, font=("Segoe UI", 9), fg=TEXT_TITLE, bg=BG_BOX, width=12, anchor="w").pack(side=tk.LEFT)

                pct = min(1.0, sec / 7200.0)
                bar_c = tk.Canvas(row, height=8, bg="#11111B", highlightthickness=0)
                bar_c.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

                fill_w = int(220 * pct)
                if fill_w > 0:
                    bar_c.create_rectangle(0, 0, fill_w, 8, fill=ACCENT_GREEN if pct < 0.9 else ACCENT_RED, width=0)

                tk.Label(row, text=time_format_hm(sec), font=("Segoe UI", 9, "bold"), fg=ACCENT_CYAN, bg=BG_BOX, width=10, anchor="e").pack(side=tk.RIGHT)


class CurfewConfigDialog(tk.Toplevel):
    """Janela modal para configurar horario permitido de uso (toque de recolher)."""

    def __init__(self, parent, store: Storage):
        super().__init__(parent)
        self.title("Configurar Horário Permitido")
        self.geometry("540x420")
        self.configure(bg=BG_MAIN)
        self.transient(parent)
        self.grab_set()
        self.store = store
        self._build_ui()

    def _build_ui(self):
        pad = tk.Frame(self, bg=BG_MAIN, padx=20, pady=20)
        pad.pack(fill=tk.BOTH, expand=True)

        tk.Label(pad, text="🌙 Horário de Uso Permitido (Toque de Recolher)", font=("Segoe UI", 13, "bold"), fg=ACCENT_PURPLE, bg=BG_MAIN).pack(anchor="w", pady=(0, 4))
        tk.Label(pad, text="Define a faixa de horário em que o computador pode ser utilizado.\nFora desse horário, o desbloqueio facial e o uso são bloqueados automaticamente.", font=("Segoe UI", 9), fg=TEXT_SUB, bg=BG_MAIN, justify="left").pack(anchor="w", pady=(0, 16))

        enabled, start_val, end_val = self.store.get_curfew_config()

        self.enabled_var = tk.BooleanVar(value=enabled)
        cb = tk.Checkbutton(pad, text="Ativar restrição de horário de uso", variable=self.enabled_var, font=("Segoe UI", 10, "bold"), fg=ACCENT_CYAN, bg=BG_MAIN, selectcolor=BG_BOX, activebackground=BG_MAIN)
        cb.pack(anchor="w", pady=(0, 14))

        box = tk.Frame(pad, bg=BG_BOX, padx=14, pady=14, highlightbackground=BORDER_DEFAULT, highlightthickness=1)
        box.pack(fill=tk.X, pady=(0, 16))

        r1 = tk.Frame(box, bg=BG_BOX)
        r1.pack(fill=tk.X, pady=4)
        tk.Label(r1, text="Liberar acesso a partir das:", font=("Segoe UI", 9, "bold"), fg=TEXT_TITLE, bg=BG_BOX).pack(side=tk.LEFT)
        self.start_entry = tk.Entry(r1, font=("Segoe UI", 10, "bold"), width=8, bg="#11111B", fg=ACCENT_CYAN, justify="center")
        self.start_entry.insert(0, start_val)
        self.start_entry.pack(side=tk.RIGHT)

        r2 = tk.Frame(box, bg=BG_BOX)
        r2.pack(fill=tk.X, pady=4)
        tk.Label(r2, text="Encerrar acesso (bloquear) às:", font=("Segoe UI", 9, "bold"), fg=TEXT_TITLE, bg=BG_BOX).pack(side=tk.LEFT)
        self.end_entry = tk.Entry(r2, font=("Segoe UI", 10, "bold"), width=8, bg="#11111B", fg=ACCENT_RED, justify="center")
        self.end_entry.insert(0, end_val)
        self.end_entry.pack(side=tk.RIGHT)

        presets_frame = tk.Frame(pad, bg=BG_MAIN)
        presets_frame.pack(fill=tk.X, pady=(0, 16))
        tk.Label(presets_frame, text="Sugestões:", font=("Segoe UI", 8), fg=TEXT_SUB, bg=BG_MAIN).pack(side=tk.LEFT, padx=(0, 6))

        for s, e, lbl in [("08:00", "20:00", "08h às 20h"), ("07:00", "21:00", "07h às 21h"), ("09:00", "19:00", "09h às 19h")]:
            def _apply(s=s, e=e):
                self.start_entry.delete(0, tk.END)
                self.start_entry.insert(0, s)
                self.end_entry.delete(0, tk.END)
                self.end_entry.insert(0, e)
            btn = tk.Button(presets_frame, text=lbl, font=("Segoe UI", 8), bg=BG_BOX, fg=TEXT_TITLE, relief=tk.FLAT, cursor="hand2", padx=6, pady=2, command=_apply)
            btn.pack(side=tk.LEFT, padx=3)

        btn_bar = tk.Frame(pad, bg=BG_MAIN)
        btn_bar.pack(fill=tk.X)
        save_btn = tk.Button(btn_bar, text="💾 Salvar Horário", font=("Segoe UI", 9, "bold"), bg=ACCENT_PURPLE, fg="#0B0B12", relief=tk.FLAT, cursor="hand2", padx=16, pady=6, command=self._save)
        save_btn.pack(side=tk.RIGHT)

    def _save(self):
        from datetime import datetime
        s = self.start_entry.get().strip()
        e = self.end_entry.get().strip()
        try:
            datetime.strptime(s, "%H:%M")
            datetime.strptime(e, "%H:%M")
        except ValueError:
            messagebox.showerror("Formato Inválido", "Informe os horários no formato HH:MM (ex: 08:00 e 20:00).", parent=self)
            return

        self.store.set_curfew_config(self.enabled_var.get(), s, e)
        status_txt = f"Horário de uso configurado: {s} às {e} (Ativo: {'Sim' if self.enabled_var.get() else 'Não'})"
        messagebox.showinfo("Sucesso", status_txt, parent=self)
        self.destroy()


class PinConfigDialog(tk.Toplevel):
    """Janela modal para configurar ou remover o PIN do Painel dos Pais."""

    def __init__(self, parent, store: Storage):
        super().__init__(parent)
        self.title("Configurar PIN de Acesso dos Pais")
        self.geometry("460x340")
        self.configure(bg=BG_MAIN)
        self.transient(parent)
        self.grab_set()
        self.store = store
        self._build_ui()

    def _build_ui(self):
        pad = tk.Frame(self, bg=BG_MAIN, padx=20, pady=20)
        pad.pack(fill=tk.BOTH, expand=True)

        has_pin = self.store.get_parent_pin() is not None

        tk.Label(pad, text="🔒 PIN de Proteção do Painel", font=("Segoe UI", 13, "bold"), fg=ACCENT_BLUE, bg=BG_MAIN).pack(anchor="w", pady=(0, 4))
        status_txt = "Atualmente: PIN ativado" if has_pin else "Atualmente: Sem proteção de PIN (abertura direta)"
        tk.Label(pad, text=status_txt, font=("Segoe UI", 9), fg=ACCENT_GREEN if has_pin else TEXT_SUB, bg=BG_MAIN).pack(anchor="w", pady=(0, 16))

        box = tk.Frame(pad, bg=BG_BOX, padx=14, pady=14, highlightbackground=BORDER_DEFAULT, highlightthickness=1)
        box.pack(fill=tk.X, pady=(0, 16))

        r1 = tk.Frame(box, bg=BG_BOX)
        r1.pack(fill=tk.X, pady=4)
        tk.Label(r1, text="Novo PIN (4 a 8 números):", font=("Segoe UI", 9, "bold"), fg=TEXT_TITLE, bg=BG_BOX).pack(side=tk.LEFT)
        self.pin_entry = tk.Entry(r1, font=("Segoe UI", 10, "bold"), width=10, bg="#11111B", fg=ACCENT_CYAN, show="*", justify="center")
        self.pin_entry.pack(side=tk.RIGHT)

        r2 = tk.Frame(box, bg=BG_BOX)
        r2.pack(fill=tk.X, pady=4)
        tk.Label(r2, text="Confirmar Novo PIN:", font=("Segoe UI", 9, "bold"), fg=TEXT_TITLE, bg=BG_BOX).pack(side=tk.LEFT)
        self.confirm_entry = tk.Entry(r2, font=("Segoe UI", 10, "bold"), width=10, bg="#11111B", fg=ACCENT_CYAN, show="*", justify="center")
        self.confirm_entry.pack(side=tk.RIGHT)

        btn_bar = tk.Frame(pad, bg=BG_MAIN)
        btn_bar.pack(fill=tk.X)

        if has_pin:
            rem_btn = tk.Button(btn_bar, text="🗑️ Desativar PIN", font=("Segoe UI", 9), bg=BG_BOX, fg=ACCENT_RED, relief=tk.FLAT, cursor="hand2", padx=10, pady=5, command=self._remove_pin)
            rem_btn.pack(side=tk.LEFT)

        save_btn = tk.Button(btn_bar, text="💾 Salvar PIN", font=("Segoe UI", 9, "bold"), bg=ACCENT_BLUE, fg="#0B0B12", relief=tk.FLAT, cursor="hand2", padx=14, pady=5, command=self._save_pin)
        save_btn.pack(side=tk.RIGHT)

    def _save_pin(self):
        p1 = self.pin_entry.get().strip()
        p2 = self.confirm_entry.get().strip()
        if not p1 or len(p1) < 4 or len(p1) > 8 or not p1.isdigit():
            messagebox.showerror("PIN Inválido", "O PIN deve conter de 4 a 8 dígitos numéricos.", parent=self)
            return
        if p1 != p2:
            messagebox.showerror("Erro", "Os dois PINs digitados não são iguais.", parent=self)
            return
        self.store.set_parent_pin(p1)
        messagebox.showinfo("PIN Salvo", "PIN parental configurado com sucesso!", parent=self)
        self.destroy()

    def _remove_pin(self):
        if messagebox.askyesno("Remover PIN", "Deseja desativar a proteção por PIN deste painel?", parent=self):
            self.store.set_parent_pin(None)
            messagebox.showinfo("PIN Removido", "Proteção por PIN desativada.", parent=self)
            self.destroy()


class AdminDashboard(tk.Tk):
    """Janela principal do Painel de Controle dos Pais."""

    def __init__(self):
        super().__init__()
        self.withdraw()  # Esconde enquanto monta

        # Validar conta
        if not is_admin_account():
            messagebox.showerror(
                "Acesso Não Permitido",
                "Este Painel de Gerenciamento é exclusivo da conta dos Pais (MarcosMiniPC).\n"
                "Ele não pode ser executado na conta Filhos por motivos de segurança.",
            )
            self.destroy()
            sys.exit(1)

        self.title("FaceControl Kids — Painel de Controle dos Pais")
        self.geometry("1040x720")
        self.minsize(880, 600)
        self.configure(bg=BG_MAIN)

        # Referencia de banco
        self.db_path = child_pilot_database()
        self.store = Storage(self.db_path)

        # Validar PIN se configurado
        if not self._check_pin_on_startup():
            self.store.close()
            self.destroy()
            return

        # Imagens em cache para evitar garbage collection do Tkinter
        self.avatar_images = {}
        self.active_enrollment_proc = None

        self._build_ui()
        self.deiconify()
        self.refresh()

    def _build_ui(self):
        # 1. Top Bar / Header
        header = tk.Frame(self, bg=BG_HEADER, height=75, highlightbackground=BORDER_DEFAULT, highlightthickness=1)
        header.pack(fill=tk.X, side=tk.TOP)

        title_frame = tk.Frame(header, bg=BG_HEADER, padx=20, pady=12)
        title_frame.pack(side=tk.LEFT)

        app_title = tk.Label(
            title_frame,
            text="🛡️ FaceControl Kids",
            font=("Segoe UI", 16, "bold"),
            fg=ACCENT_BLUE,
            bg=BG_HEADER,
        )
        app_title.pack(anchor="w")

        app_sub = tk.Label(
            title_frame,
            text="Painel Parental • Gerenciamento de Filhos, Fotos e Quotas de Tempo",
            font=("Segoe UI", 9),
            fg=TEXT_SUB,
            bg=BG_HEADER,
        )
        app_sub.pack(anchor="w")

        # Botoes Superiores
        top_btn_frame = tk.Frame(header, bg=BG_HEADER, padx=20, pady=16)
        top_btn_frame.pack(side=tk.RIGHT)

        history_btn = tk.Button(
            top_btn_frame,
            text="📊 Histórico 7 Dias",
            font=("Segoe UI", 9, "bold"),
            bg=BG_BOX,
            fg=ACCENT_GREEN,
            activebackground=BG_BOX_HOVER,
            activeforeground=ACCENT_GREEN,
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=6,
            command=self._open_history,
        )
        history_btn.pack(side=tk.LEFT, padx=4)

        curfew_btn = tk.Button(
            top_btn_frame,
            text="🌙 Horário Permitido",
            font=("Segoe UI", 9, "bold"),
            bg=BG_BOX,
            fg=ACCENT_PURPLE,
            activebackground=BG_BOX_HOVER,
            activeforeground=ACCENT_PURPLE,
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=6,
            command=self._open_curfew,
        )
        curfew_btn.pack(side=tk.LEFT, padx=4)

        pin_btn = tk.Button(
            top_btn_frame,
            text="🔒 PIN",
            font=("Segoe UI", 9, "bold"),
            bg=BG_BOX,
            fg=ACCENT_YELLOW,
            activebackground=BG_BOX_HOVER,
            activeforeground=ACCENT_YELLOW,
            relief=tk.FLAT,
            cursor="hand2",
            padx=8,
            pady=6,
            command=self._open_pin_config,
        )
        pin_btn.pack(side=tk.LEFT, padx=4)

        programs_btn = tk.Button(
            top_btn_frame,
            text="🚀 Programas",
            font=("Segoe UI", 9, "bold"),
            bg=BG_BOX,
            fg=ACCENT_CYAN,
            activebackground=BG_BOX_HOVER,
            activeforeground=ACCENT_CYAN,
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=6,
            command=self._open_programs_config,
        )
        programs_btn.pack(side=tk.LEFT, padx=4)

        refresh_btn = tk.Button(
            top_btn_frame,
            text="🔄",
            font=("Segoe UI", 9, "bold"),
            bg=BG_BOX,
            fg=TEXT_TITLE,
            activebackground=BG_BOX_HOVER,
            activeforeground=TEXT_TITLE,
            relief=tk.FLAT,
            cursor="hand2",
            padx=8,
            pady=6,
            command=self.refresh,
        )
        refresh_btn.pack(side=tk.LEFT, padx=4)

        add_child_btn = tk.Button(
            top_btn_frame,
            text="➕ Nova Criança",
            font=("Segoe UI", 9, "bold"),
            bg=ACCENT_BLUE,
            fg="#0B0B12",
            activebackground=ACCENT_CYAN,
            activeforeground="#0B0B12",
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=6,
            command=self._add_child,
        )
        add_child_btn.pack(side=tk.LEFT, padx=4)

        # 2. Barra de Status e Dica
        self.status_bar = tk.Frame(self, bg=BG_MAIN, padx=24, pady=8)
        self.status_bar.pack(fill=tk.X)

        self.status_text = tk.StringVar(value="Pronto • Todas as alterações são salvas e aplicadas em tempo real.")
        tk.Label(
            self.status_bar,
            textvariable=self.status_text,
            font=("Segoe UI", 9),
            fg=ACCENT_GREEN,
            bg=BG_MAIN,
        ).pack(side=tk.LEFT)

        # 3. Area Principal com Scroll para os Cards
        main_container = tk.Frame(self, bg=BG_MAIN, padx=20, pady=10)
        main_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(main_container, bg=BG_MAIN, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(main_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.cards_frame = tk.Frame(self.canvas, bg=BG_MAIN)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")

        self.cards_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width),
        )

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh(self):
        """Atualiza os dados lendo diretamente do SQLite compartilhado."""
        for w in self.cards_frame.winfo_children():
            w.destroy()

        self.avatar_images.clear()
        people = self.store.people()

        if not people:
            empty_box = tk.Frame(self.cards_frame, bg=BG_CARD, padx=30, pady=30)
            empty_box.pack(fill=tk.X, pady=20)
            tk.Label(
                empty_box,
                text="Nenhum perfil de criança encontrado no banco de dados.",
                font=("Segoe UI", 12),
                fg=TEXT_SUB,
                bg=BG_CARD,
            ).pack()
            return

        today = date.today().isoformat()

        # Renderizar cada crianca
        for pid, name, limit_seconds in people:
            samples = self.store.enrollment_count(pid)
            used_seconds = self.store.used(pid, today)
            bonus_seconds = self.store.bonus(pid, today)
            rem_seconds = self.store.remaining(pid, today)
            limit_min = limit_seconds // 60

            self._create_child_card(
                child_id=pid,
                name=name,
                samples=samples,
                limit_min=limit_min,
                used_sec=used_seconds,
                bonus_sec=bonus_seconds,
                rem_sec=rem_seconds,
            )

    def _create_child_card(
        self,
        child_id: int,
        name: str,
        samples: int,
        limit_min: int,
        used_sec: float,
        bonus_sec: int,
        rem_sec: float,
    ):
        """Cria o card individual para uma crianca com avatar, acoes e controle de tempo."""
        card = tk.Frame(
            self.cards_frame,
            bg=BG_CARD,
            highlightbackground=BORDER_DEFAULT,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        card.pack(fill=tk.X, pady=10)

        # Linha 1: Cabecalho do Card (Badge de Perfil + Status de Biometria)
        header_row = tk.Frame(card, bg=BG_CARD)
        header_row.pack(fill=tk.X, pady=(0, 10))

        badge = tk.Label(
            header_row,
            text=f"PERFIL #{child_id}",
            font=("Segoe UI", 9, "bold"),
            fg=ACCENT_CYAN,
            bg=BG_BOX,
            padx=8,
            pady=2,
        )
        badge.pack(side=tk.LEFT)

        status_text = f"● {samples} amostras cadastradas" if samples > 0 else "○ Sem biometria cadastrada"
        status_color = ACCENT_GREEN if samples > 0 else TEXT_MUTED
        status_label = tk.Label(
            header_row,
            text=status_text,
            font=("Segoe UI", 9, "bold"),
            fg=status_color,
            bg=BG_CARD,
        )
        status_label.pack(side=tk.RIGHT)

        # Linha 2: Conteudo Principal (Avatar a Esquerda, Detalhes e Acoes a Direita)
        body = tk.Frame(card, bg=BG_CARD)
        body.pack(fill=tk.X)

        # Coluna do Avatar
        avatar_col = tk.Frame(body, bg=BG_CARD, width=130)
        avatar_col.pack(side=tk.LEFT, padx=(0, 20), anchor="n")

        avatar_path = get_child_avatar_path(child_id)
        if avatar_path and avatar_path.exists():
            try:
                img = tk.PhotoImage(file=str(avatar_path))
                self.avatar_images[child_id] = img  # Armazena referencia viva
                avatar_lbl = tk.Label(avatar_col, image=img, bg=BG_CARD)
                avatar_lbl.pack()
            except Exception:
                self._draw_fallback_avatar(avatar_col, name)
        else:
            self._draw_fallback_avatar(avatar_col, name)

        # Coluna de Informacoes e Controles
        info_col = tk.Frame(body, bg=BG_CARD)
        info_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Nome e Botao Renomear
        name_row = tk.Frame(info_col, bg=BG_CARD)
        name_row.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            name_row,
            text=name,
            font=("Segoe UI", 16, "bold"),
            fg=TEXT_TITLE,
            bg=BG_CARD,
        ).pack(side=tk.LEFT)

        rename_btn = tk.Button(
            name_row,
            text="✏️ Renomear",
            font=("Segoe UI", 8, "bold"),
            bg=BG_BOX,
            fg=ACCENT_BLUE,
            relief=tk.FLAT,
            cursor="hand2",
            padx=8,
            pady=2,
            command=lambda cid=child_id, cname=name: self._rename_child(cid, cname),
        )
        rename_btn.pack(side=tk.LEFT, padx=(12, 0))

        tk.Label(
            avatar_col,
            text="Foto da\nboas-vindas",
            font=("Segoe UI", 8, "bold"),
            fg=TEXT_SUB,
            bg=BG_CARD,
            justify="center",
        ).pack(pady=(5, 0))

        # A foto visual e a biometria sao controles independentes.
        photo_btn_row = tk.Frame(info_col, bg=BG_CARD)
        photo_btn_row.pack(fill=tk.X, pady=(4, 12))

        pick_file_btn = tk.Button(
            photo_btn_row,
            text="🖼️ Escolher Foto da Boas-Vindas",
            font=("Segoe UI", 9, "bold"),
            bg=BG_BOX,
            fg=ACCENT_CYAN,
            activebackground=BG_BOX_HOVER,
            activeforeground=ACCENT_CYAN,
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=5,
            command=lambda cid=child_id: self._pick_photo_file(cid),
        )
        pick_file_btn.pack(side=tk.LEFT, padx=(0, 8))

        webcam_btn = tk.Button(
            photo_btn_row,
            text="📷 Cadastrar com Webcam",
            font=("Segoe UI", 9, "bold"),
            bg=BG_BOX,
            fg=ACCENT_BLUE,
            activebackground=BG_BOX_HOVER,
            activeforeground=ACCENT_BLUE,
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=5,
            command=lambda cid=child_id: self._enroll_webcam(cid),
        )
        webcam_btn.pack(side=tk.LEFT, padx=(0, 8))

        if samples > 0 or avatar_path:
            clear_btn = tk.Button(
                photo_btn_row,
                text="🗑️ Limpar Biometria",
                font=("Segoe UI", 9),
                bg=BG_BOX,
                fg=ACCENT_RED,
                activebackground=BG_BOX_HOVER,
                activeforeground=ACCENT_RED,
                relief=tk.FLAT,
                cursor="hand2",
                padx=8,
                pady=5,
                command=lambda cid=child_id, cname=name: self._clear_biometrics(cid, cname),
            )
            clear_btn.pack(side=tk.LEFT)

        # Card Interno: Gerenciamento de Tempo e Quota
        quota_box = tk.Frame(info_col, bg=BG_BOX, padx=14, pady=12, highlightbackground=BORDER_DEFAULT, highlightthickness=1)
        quota_box.pack(fill=tk.X)

        # Linha de Quota Atual
        time_info_row = tk.Frame(quota_box, bg=BG_BOX)
        time_info_row.pack(fill=tk.X, pady=(0, 6))

        rem_str = time_format_hm(rem_sec)
        limit_str = time_format_hm(limit_min * 60)
        used_str = time_format_hm(used_sec)
        bonus_str = time_format_hm(bonus_sec)

        tk.Label(
            time_info_row,
            text=f"⏱️ Tempo Restante Hoje: {rem_str}",
            font=("Segoe UI", 10, "bold"),
            fg=ACCENT_GREEN if rem_sec > 1800 else ACCENT_YELLOW if rem_sec > 0 else ACCENT_RED,
            bg=BG_BOX,
        ).pack(side=tk.LEFT)

        tk.Label(
            time_info_row,
            text=f"Usado: {used_str}  |  Limite: {limit_str}  |  Bônus hoje: {bonus_str}",
            font=("Segoe UI", 9),
            fg=TEXT_MUTED,
            bg=BG_BOX,
        ).pack(side=tk.RIGHT)

        # Barra visual de progresso
        total_quota_sec = max(1, (limit_min * 60) + bonus_sec)
        pct = max(0.0, min(1.0, rem_sec / total_quota_sec))
        bar_canvas = tk.Canvas(quota_box, height=6, bg="#11111B", highlightthickness=0)
        bar_canvas.pack(fill=tk.X, pady=(2, 10))

        def _draw_bar(evt, c=bar_canvas, p=pct):
            w = evt.width
            c.delete("all")
            fill_w = int(w * p)
            if fill_w > 0:
                color = ACCENT_GREEN if p > 0.25 else ACCENT_RED
                c.create_rectangle(0, 0, fill_w, 6, fill=color, width=0)

        bar_canvas.bind("<Configure>", _draw_bar)

        # Linha de Controles de Limite e Bonus
        controls_row = tk.Frame(quota_box, bg=BG_BOX)
        controls_row.pack(fill=tk.X)

        tk.Label(
            controls_row,
            text="Ajustar Limite Diário:",
            font=("Segoe UI", 8, "bold"),
            fg=TEXT_SUB,
            bg=BG_BOX,
        ).pack(side=tk.LEFT, padx=(0, 6))

        for m, label in [(60, "1h"), (90, "1h30"), (120, "2h"), (180, "3h")]:
            btn = tk.Button(
                controls_row,
                text=label,
                font=("Segoe UI", 8, "bold" if limit_min == m else "normal"),
                bg=ACCENT_BLUE if limit_min == m else "#11111B",
                fg="#0B0B12" if limit_min == m else TEXT_TITLE,
                relief=tk.FLAT,
                cursor="hand2",
                padx=6,
                pady=1,
                command=lambda cid=child_id, val=m: self._set_limit(cid, val),
            )
            btn.pack(side=tk.LEFT, padx=2)

        custom_btn = tk.Button(
            controls_row,
            text="Outro...",
            font=("Segoe UI", 8),
            bg="#11111B",
            fg=TEXT_SUB,
            relief=tk.FLAT,
            cursor="hand2",
            padx=6,
            pady=1,
            command=lambda cid=child_id, cur=limit_min: self._set_custom_limit(cid, cur),
        )
        custom_btn.pack(side=tk.LEFT, padx=2)

        # Concessao de Bonus
        bonus_frame = tk.Frame(controls_row, bg=BG_BOX)
        bonus_frame.pack(side=tk.RIGHT)

        tk.Label(
            bonus_frame,
            text="Dar Bônus Hoje:",
            font=("Segoe UI", 8, "bold"),
            fg=ACCENT_YELLOW,
            bg=BG_BOX,
        ).pack(side=tk.LEFT, padx=(0, 6))

        for b_min in [15, 30, 60]:
            b_btn = tk.Button(
                bonus_frame,
                text=f"+{b_min}m",
                font=("Segoe UI", 8, "bold"),
                bg="#11111B",
                fg=ACCENT_YELLOW,
                relief=tk.FLAT,
                cursor="hand2",
                padx=6,
                pady=1,
                command=lambda cid=child_id, minutes=b_min: self._give_bonus(cid, minutes),
            )
            b_btn.pack(side=tk.LEFT, padx=2)

        # Campo personalizado para digitar os minutos de bônus
        custom_bonus_var = tk.StringVar()
        bonus_entry = tk.Entry(
            bonus_frame,
            textvariable=custom_bonus_var,
            font=("Segoe UI", 8, "bold"),
            width=4,
            bg="#11111B",
            fg=ACCENT_YELLOW,
            insertbackground=ACCENT_YELLOW,
            highlightbackground=BORDER_DEFAULT,
            highlightcolor=ACCENT_YELLOW,
            highlightthickness=1,
            relief=tk.FLAT,
            justify="center",
        )
        bonus_entry.pack(side=tk.LEFT, padx=(6, 2))

        tk.Label(
            bonus_frame,
            text="min",
            font=("Segoe UI", 8),
            fg=TEXT_SUB,
            bg=BG_BOX,
        ).pack(side=tk.LEFT, padx=(0, 3))

        def _apply_custom_bonus(cid=child_id, var=custom_bonus_var):
            val = var.get().strip()
            if not val:
                return
            try:
                m = int(val)
                if not (1 <= m <= 480):
                    raise ValueError("Informe entre 1 e 480 minutos.")
                self._give_bonus(cid, m)
                var.set("")
            except ValueError as err:
                messagebox.showerror("Bônus Inválido", f"Valor inválido: {err}", parent=self)

        apply_btn = tk.Button(
            bonus_frame,
            text="+",
            font=("Segoe UI", 8, "bold"),
            bg=ACCENT_YELLOW,
            fg="#0B0B12",
            activebackground="#FFF0BA",
            activeforeground="#0B0B12",
            relief=tk.FLAT,
            cursor="hand2",
            padx=6,
            pady=1,
            command=_apply_custom_bonus,
        )
        apply_btn.pack(side=tk.LEFT, padx=1)
        bonus_entry.bind("<Return>", lambda e: _apply_custom_bonus())

    def _draw_fallback_avatar(self, parent, name: str):
        """Desenha avatar circular placeholder com a inicial quando nao ha foto."""
        canvas = tk.Canvas(parent, width=100, height=100, bg=BG_CARD, highlightthickness=0)
        canvas.pack()
        canvas.create_oval(6, 6, 94, 94, fill=BG_BOX, outline=ACCENT_BLUE, width=2)
        initial = name[0].upper() if name else "F"
        canvas.create_text(50, 50, text=initial, font=("Segoe UI", 32, "bold"), fill=ACCENT_CYAN)

    def _pick_photo_file(self, child_id: int):
        """Seleciona apenas a foto visual; a biometria continua independente."""
        file_path = filedialog.askopenfilename(
            title=f"Escolher Foto para o Perfil #{child_id}",
            filetypes=[
                ("Arquivos de Imagem", "*.jpg;*.jpeg;*.png;*.bmp;*.webp"),
                ("Todos os Arquivos", "*.*"),
            ],
            parent=self,
        )
        if not file_path:
            return

        self.status_text.set("Processando a foto da tela de boas-vindas...")
        self.update_idletasks()

        res = set_child_photo_from_file(
            child_id=child_id,
            file_path=file_path,
            models_dir=MODELS_DIR if MODELS_DIR.exists() else None,
            store=self.store,
            update_biometrics=False,
        )

        if res.success:
            messagebox.showinfo("Foto Atualizada", res.message, parent=self)
            self.status_text.set(f"Foto de boas-vindas do perfil #{child_id} atualizada com sucesso!")
        else:
            messagebox.showerror("Aviso", res.message, parent=self)
            self.status_text.set("Falha ao atualizar foto.")

        self.refresh()

    def _enroll_webcam(self, child_id: int):
        """Inicia o processo de cadastro consentido guiado via webcam (12 amostras)."""
        if self.active_enrollment_proc is not None and self.active_enrollment_proc.poll() is None:
            messagebox.showwarning(
                "Processo em Andamento",
                "Já existe um processo de cadastro de webcam aberto. Conclua ou feche a janela da câmera primeiro.",
                parent=self,
            )
            return

        # Executa children_pilot enroll <id>
        cmd = [sys.executable, "-m", "facekids.children_pilot", "enroll", str(child_id)]
        try:
            self.active_enrollment_proc = subprocess.Popen(cmd, cwd=str(ROOT_DIR))
            self.status_text.set(f"Janela de captura da webcam aberta para o Perfil #{child_id}...")

            # Thread para aguardar termino e atualizar UI
            def _wait_completion():
                self.active_enrollment_proc.wait()
                self.after(500, self._on_enrollment_finished, child_id)

            threading.Thread(target=_wait_completion, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Erro ao Iniciar Webcam", f"Não foi possível iniciar o cadastro: {e}", parent=self)

    def _on_enrollment_finished(self, child_id: int):
        self.status_text.set(f"Cadastro via webcam finalizado para o Perfil #{child_id}.")
        self.refresh()

    def _rename_child(self, child_id: int, current_name: str):
        """Permite alterar o nome do filho no SQLite."""
        new_name = simpledialog.askstring(
            "Alterar Nome",
            f"Informe o novo nome para o Perfil #{child_id}:",
            initialvalue=current_name,
            parent=self,
        )
        if not new_name or not new_name.strip():
            return
        try:
            self.store.update_person_name(child_id, new_name.strip())
            self.status_text.set(f"Perfil #{child_id} renomeado para '{new_name.strip()}'.")
            self.refresh()
        except Exception as e:
            messagebox.showerror("Erro ao Renomear", str(e), parent=self)

    def _set_limit(self, child_id: int, minutes: int):
        """Altera o limite diario em minutos."""
        try:
            self.store.set_daily_limit(child_id, minutes)
            self.status_text.set(f"Limite diário do Perfil #{child_id} alterado para {minutes} min.")
            self.refresh()
        except Exception as e:
            messagebox.showerror("Erro", str(e), parent=self)

    def _set_custom_limit(self, child_id: int, current_val: int):
        minutes = simpledialog.askinteger(
            "Limite Personalizado",
            f"Defina o limite diário em minutos (1 a 1440):",
            initialvalue=current_val,
            minvalue=1,
            maxvalue=1440,
            parent=self,
        )
        if minutes is not None:
            self._set_limit(child_id, minutes)

    def _give_bonus(self, child_id: int, minutes: int):
        """Concede bonus de tempo para hoje."""
        try:
            self.store.add_bonus(child_id, minutes)
            self.status_text.set(f"Bônus de +{minutes} min concedido com sucesso!")
            self.refresh()
        except Exception as e:
            messagebox.showerror("Erro ao Conceder Bônus", str(e), parent=self)

    def _clear_biometrics(self, child_id: int, name: str):
        """Remove os modelos e fotos da crianca."""
        confirmed = messagebox.askyesno(
            "Confirmar Limpeza",
            f"Deseja realmente remover os modelos faciais e fotos cadastradas de '{name}'?\n\n"
            "O saldo de tempo e histórico serão preservados.",
            icon="warning",
            parent=self,
        )
        if not confirmed:
            return

        try:
            self.store.remove_embeddings(child_id)
            remove_child_avatar_files(child_id)
            self.status_text.set(f"Biometria e fotos de '{name}' foram removidas com sucesso.")
            self.refresh()
        except Exception as e:
            messagebox.showerror("Erro", str(e), parent=self)

    def _add_child(self):
        """Permite adicionar uma nova crianca ao sistema."""
        name = simpledialog.askstring("Nova Criança", "Nome da criança:", parent=self)
        if not name or not name.strip():
            return
        limit = simpledialog.askinteger(
            "Limite Diário",
            "Limite diário de tempo em minutos (ex: 120 para 2 horas):",
            initialvalue=120,
            minvalue=1,
            maxvalue=1440,
            parent=self,
        )
        if limit is None:
            return
        try:
            cid = self.store.add_person(name.strip(), limit)
            self.status_text.set(f"Criança '{name.strip()}' cadastrada com ID #{cid}!")
            self.refresh()
        except Exception as e:
            messagebox.showerror("Erro ao Cadastrar", str(e), parent=self)

    def _open_programs_config(self):
        """Abre a janela de configuracao de programas de inicializacao."""
        ProgramsConfigDialog(self)

    def _open_history(self):
        """Abre o historico de uso dos ultimos 7 dias."""
        WeeklyUsageDialog(self, self.store)

    def _open_curfew(self):
        """Abre o dialogo de configuracao de horario permitido."""
        CurfewConfigDialog(self, self.store)

    def _open_pin_config(self):
        """Abre o dialogo para cadastrar, alterar ou remover o PIN de acesso."""
        PinConfigDialog(self, self.store)

    def _check_pin_on_startup(self) -> bool:
        """Solicita o PIN parental caso esteja configurado no banco de dados."""
        stored = self.store.get_parent_pin()
        if stored is None:
            return True
        for attempt in range(3):
            pin = simpledialog.askstring("Acesso dos Pais", "Informe o PIN parental para acessar o painel:", show="*", parent=self)
            if pin is None:
                return False
            if self.store.verify_parent_pin(pin):
                return True
            messagebox.showwarning("PIN Incorreto", f"PIN incorreto. Tentativa {attempt + 1} de 3.", parent=self)
        return False


def main():
    app = AdminDashboard()
    app.mainloop()


if __name__ == "__main__":
    main()
