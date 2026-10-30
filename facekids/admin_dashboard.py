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
from pathlib import Path
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from .avatar_utils import (
    get_child_avatar_path,
    save_child_photo,
    set_child_photo_from_file,
    remove_child_avatar_files,
    AVATAR_DIR,
)
from .storage import Storage
from .parent_ui_state import filter_children, load_overview, screen_time_label, validate_schedule
from .ui_theme import THEMES, load_theme, save_theme, theme_palette
from .children_pilot import child_pilot_database, windows_token_user
from .platform_paths import application_data_dir

logger = logging.getLogger("FaceKidsAdmin")

ROOT_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT_DIR / "models"
PROGRAMS_FILE = application_data_dir() / "programas_inicializar.json"

# The classic palette is unchanged. Theme changes rebuild Tk widgets with
# these active module-level roles, including existing dialogs and card canvases.
def _activate_theme(name: str) -> None:
    globals().update(theme_palette(name))


_activate_theme("Atual")


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
                    "name": "Brave",
                    "executable": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                    "arguments": "",
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
            fg=TEXT_ON_ACCENT,
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
                selectcolor=BG_FIELD,
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
                bar_c = tk.Canvas(row, height=8, bg=BG_FIELD, highlightthickness=0)
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
        self.start_entry = tk.Entry(r1, font=("Segoe UI", 10, "bold"), width=8, bg=BG_FIELD, insertbackground=TEXT_TITLE, fg=ACCENT_CYAN, justify="center")
        self.start_entry.insert(0, start_val)
        self.start_entry.pack(side=tk.RIGHT)

        r2 = tk.Frame(box, bg=BG_BOX)
        r2.pack(fill=tk.X, pady=4)
        tk.Label(r2, text="Encerrar acesso (bloquear) às:", font=("Segoe UI", 9, "bold"), fg=TEXT_TITLE, bg=BG_BOX).pack(side=tk.LEFT)
        self.end_entry = tk.Entry(r2, font=("Segoe UI", 10, "bold"), width=8, bg=BG_FIELD, insertbackground=TEXT_TITLE, fg=ACCENT_RED, justify="center")
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
        save_btn = tk.Button(btn_bar, text="💾 Salvar Horário", font=("Segoe UI", 9, "bold"), bg=ACCENT_PURPLE, fg=TEXT_ON_ACCENT, relief=tk.FLAT, cursor="hand2", padx=16, pady=6, command=self._save)
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
        if hasattr(self.master, "refresh"):
            self.master.refresh()
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
        self.pin_entry = tk.Entry(r1, font=("Segoe UI", 10, "bold"), width=10, bg=BG_FIELD, insertbackground=TEXT_TITLE, fg=ACCENT_CYAN, show="*", justify="center")
        self.pin_entry.pack(side=tk.RIGHT)

        r2 = tk.Frame(box, bg=BG_BOX)
        r2.pack(fill=tk.X, pady=4)
        tk.Label(r2, text="Confirmar Novo PIN:", font=("Segoe UI", 9, "bold"), fg=TEXT_TITLE, bg=BG_BOX).pack(side=tk.LEFT)
        self.confirm_entry = tk.Entry(r2, font=("Segoe UI", 10, "bold"), width=10, bg=BG_FIELD, insertbackground=TEXT_TITLE, fg=ACCENT_CYAN, show="*", justify="center")
        self.confirm_entry.pack(side=tk.RIGHT)

        btn_bar = tk.Frame(pad, bg=BG_MAIN)
        btn_bar.pack(fill=tk.X)

        if has_pin:
            rem_btn = tk.Button(btn_bar, text="🗑️ Desativar PIN", font=("Segoe UI", 9), bg=BG_BOX, fg=ACCENT_RED, relief=tk.FLAT, cursor="hand2", padx=10, pady=5, command=self._remove_pin)
            rem_btn.pack(side=tk.LEFT)

        save_btn = tk.Button(btn_bar, text="💾 Salvar PIN", font=("Segoe UI", 9, "bold"), bg=ACCENT_BLUE, fg=TEXT_ON_ACCENT, relief=tk.FLAT, cursor="hand2", padx=14, pady=5, command=self._save_pin)
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

        self.theme_name = load_theme()
        _activate_theme(self.theme_name)

        self.title("FaceControl Kids — Painel de Controle dos Pais")
        self.geometry("1180x780")
        self.minsize(960, 620)
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

        # Three user-selectable palettes; persist only in the parent profile,
        # never in the shared child SQLite or the Windows authentication path.
        selector = tk.Frame(header, bg=BG_HEADER, padx=18, pady=12)
        selector.pack(side=tk.RIGHT)
        tk.Label(
            selector, text="Tema das cores", bg=BG_HEADER, fg=TEXT_SUB,
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(0, 9))
        self.theme_var = tk.StringVar(value=self.theme_name)
        chooser = tk.OptionMenu(
            selector, self.theme_var, *THEMES.keys(), command=self._change_theme
        )
        chooser.configure(
            bg=BG_BOX, fg=TEXT_TITLE, activebackground=BG_BOX_HOVER,
            activeforeground=TEXT_TITLE, relief=tk.FLAT, bd=0,
            highlightthickness=1, highlightbackground=BORDER_DEFAULT,
            cursor="hand2", font=("Segoe UI", 10, "bold"),
            width=8, padx=7, pady=5,
        )
        chooser["menu"].configure(
            bg=BG_BOX, fg=TEXT_TITLE, activebackground=BG_BOX_HOVER,
            activeforeground=TEXT_TITLE, font=("Segoe UI", 10),
        )
        chooser.pack(side=tk.LEFT)

        # Botoes Superiores
        # Navigation lives below the brand header, so all actions remain visible
        # on a 960px wide laptop screen (instead of overflowing on the right).
        top_btn_frame = tk.Frame(self, bg=BG_MAIN, padx=20, pady=10)
        top_btn_frame.pack(fill=tk.X, side=tk.TOP)

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
            fg=TEXT_ON_ACCENT,
            activebackground=ACCENT_CYAN,
            activeforeground=TEXT_ON_ACCENT,
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

        # 3. Overview: four compact metrics and an always-visible search.
        overview_bar = tk.Frame(self, bg=BG_MAIN, padx=20, pady=6)
        overview_bar.pack(fill=tk.X)
        overview_heading = tk.Frame(overview_bar, bg=BG_MAIN)
        overview_heading.pack(fill=tk.X, pady=(0, 9))
        tk.Label(overview_heading, text="Visão geral", bg=BG_MAIN, fg=TEXT_TITLE,
                 font=("Segoe UI", 15, "bold")).pack(side=tk.LEFT)
        self.result_counter = tk.StringVar(value="")
        tk.Label(overview_heading, textvariable=self.result_counter, bg=BG_MAIN,
                 fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(12, 0))
        search_row = tk.Frame(overview_heading, bg=BG_MAIN)
        search_row.pack(side=tk.RIGHT)
        tk.Label(search_row, text="Buscar filho", bg=BG_MAIN, fg=TEXT_SUB,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 8))
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            search_row, textvariable=self.search_var, width=23,
            font=("Segoe UI", 10), bg=BG_BOX, fg=TEXT_TITLE,
            insertbackground=TEXT_TITLE, relief=tk.FLAT,
            highlightthickness=1, highlightbackground=BORDER_DEFAULT,
            highlightcolor=ACCENT_BLUE,
        )
        self.search_entry.pack(side=tk.LEFT, ipady=5)
        self.search_var.trace_add("write", lambda *_: self.refresh())

        metrics_row = tk.Frame(overview_bar, bg=BG_MAIN)
        metrics_row.pack(fill=tk.X)
        self.total_var = tk.StringVar(value="—")
        self.enrolled_var = tk.StringVar(value="—")
        self.remaining_var = tk.StringVar(value="—")
        self.schedule_var = tk.StringVar(value="—")
        for column, (label, value, accent) in enumerate((
            ("CRIANÇAS", self.total_var, ACCENT_CYAN),
            ("ROSTOS CADASTRADOS", self.enrolled_var, ACCENT_GREEN),
            ("SALDO TOTAL HOJE", self.remaining_var, ACCENT_BLUE),
            ("HORÁRIO DE USO", self.schedule_var, ACCENT_PURPLE),
        )):
            tile = tk.Frame(metrics_row, bg=BG_CARD, padx=13, pady=10,
                            highlightthickness=1, highlightbackground=BORDER_DEFAULT)
            tile.grid(row=0, column=column, sticky="nsew", padx=(0, 9 if column < 3 else 0))
            metrics_row.columnconfigure(column, weight=1, uniform="metrics")
            tk.Label(tile, text=label, bg=BG_CARD, fg=TEXT_MUTED,
                     font=("Segoe UI", 8, "bold")).pack(anchor="w")
            tk.Label(tile, textvariable=value, bg=BG_CARD, fg=accent,
                     font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(3, 0))

        # Global allowed-hours editor, embedded beside the quotas.
        schedule_row = tk.Frame(overview_bar, bg=BG_BOX, padx=12, pady=9,
                                highlightthickness=1, highlightbackground=BORDER_DEFAULT)
        schedule_row.pack(fill=tk.X, pady=(10, 0))
        tk.Label(schedule_row, text="Horário permitido (todos os filhos)",
                 bg=BG_BOX, fg=TEXT_TITLE, font=("Segoe UI", 10, "bold")).pack(
                     side=tk.LEFT, padx=(0, 14))
        self.schedule_enabled_var = tk.BooleanVar(value=False)
        self.schedule_start_var = tk.StringVar(value="08:00")
        self.schedule_end_var = tk.StringVar(value="20:00")
        self._schedule_loaded = None
        tk.Checkbutton(
            schedule_row, text="Ativo", variable=self.schedule_enabled_var,
            bg=BG_BOX, fg=TEXT_SUB, selectcolor=BG_CARD,
            activebackground=BG_BOX, activeforeground=TEXT_TITLE,
        ).pack(side=tk.LEFT, padx=(0, 12))
        for caption, var in (("Das", self.schedule_start_var),
                             ("até", self.schedule_end_var)):
            tk.Label(schedule_row, text=caption, bg=BG_BOX, fg=TEXT_SUB,
                     font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 5))
            tk.Entry(
                schedule_row, textvariable=var, width=6, justify="center",
                bg=BG_CARD, fg=TEXT_TITLE, insertbackground=TEXT_TITLE,
                font=("Segoe UI", 10), relief=tk.FLAT,
                highlightthickness=1, highlightbackground=BORDER_DEFAULT,
            ).pack(side=tk.LEFT, padx=(0, 10), ipady=3)
        tk.Button(
            schedule_row, text="Salvar horário", command=self._save_inline_schedule,
            bg=ACCENT_PURPLE, fg=BG_MAIN, activebackground=ACCENT_CYAN,
            activeforeground=BG_MAIN, relief=tk.FLAT, cursor="hand2",
            font=("Segoe UI", 9, "bold"), padx=10, pady=4,
        ).pack(side=tk.LEFT, padx=(2, 0))

        self.data_source_var = tk.StringVar(value="")
        tk.Label(overview_bar, textvariable=self.data_source_var, bg=BG_MAIN,
                 fg=TEXT_SUB, anchor="w", font=("Segoe UI", 9),
                 wraplength=1080, justify="left").pack(fill=tk.X, pady=(9, 0))

        # 4. Cards retain the existing enrollment, photo, bonus and quota flows.
        main_container = tk.Frame(self, bg=BG_MAIN, padx=20, pady=10)
        main_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(main_container, bg=BG_MAIN, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(main_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.cards_frame = tk.Frame(self.canvas, bg=BG_MAIN)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")

        def _update_scrollregion(event=None):
            self.cards_frame.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        def _resize_canvas(event):
            self.canvas.itemconfig(self.canvas_window, width=event.width)
            _update_scrollregion()

        self.cards_frame.bind("<Configure>", _update_scrollregion)
        self.canvas.bind("<Configure>", _resize_canvas)

        # Scrollbar DEVE ser empacotada antes do Canvas para garantir alocacao correta
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def _on_mousewheel(event):
            try:
                if self.canvas.winfo_exists():
                    # Windows event.delta e tipicamente +/- 120
                    self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        self.bind_all("<MouseWheel>", _on_mousewheel)

    def _change_theme(self, selected: str) -> None:
        """Apply immediately, rebuilding only presentation widgets.

        The enrollment subprocess, database connection, Windows session and
        authentication remain untouched. Changing a theme never asks for a
        second PIN or silently applies unsaved quota/schedule changes.
        """
        if selected == self.theme_name:
            return
        try:
            save_theme(selected)
        except (OSError, ValueError) as exc:
            self.theme_var.set(self.theme_name)
            messagebox.showerror(
                "Tema não salvo",
                f"Não foi possível salvar a preferência: {exc}", parent=self
            )
            return

        search = self.search_var.get()
        schedule_fields = (
            self.schedule_enabled_var.get(),
            self.schedule_start_var.get(),
            self.schedule_end_var.get(),
            self._schedule_loaded,
        )

        self.theme_name = selected
        _activate_theme(selected)
        self.withdraw()
        try:
            # Existing modal dialogs use grab_set(), so the user cannot change
            # the theme from the main window while one is open.
            for widget in self.winfo_children():
                if not isinstance(widget, tk.Toplevel):
                    widget.destroy()
            self.avatar_images.clear()
            self.configure(bg=BG_MAIN)
            self._build_ui()
            enabled, start, end, previous_loaded = schedule_fields
            self._schedule_loaded = previous_loaded
            self.schedule_enabled_var.set(enabled)
            self.schedule_start_var.set(start)
            self.schedule_end_var.set(end)
            self.search_var.set(search)
            self.refresh()
            self.status_text.set(f"Tema {selected} aplicado e salvo.")
        finally:
            self.deiconify()

    def _save_inline_schedule(self):
        """Apply global hours only on deliberate parent action, never during refresh."""
        try:
            enabled, start, end = validate_schedule(
                self.schedule_enabled_var.get(),
                self.schedule_start_var.get(),
                self.schedule_end_var.get(),
            )
            self.store.set_curfew_config(enabled, start, end)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Horário inválido", str(exc), parent=self)
            return
        self._schedule_loaded = (enabled, start, end)
        self.status_text.set(
            f"Horário {'ativado' if enabled else 'desativado'} • {start} às {end}"
        )
        self.refresh()

    def refresh(self):
        """Re-render UI from read-only view models; never change quota in refresh."""
        for widget in self.cards_frame.winfo_children():
            widget.destroy()
        self.avatar_images.clear()

        overview = load_overview(self.store)
        actual_schedule = (
            overview.schedule_enabled,
            overview.schedule_start,
            overview.schedule_end,
        )
        edited_schedule = (
            self.schedule_enabled_var.get(),
            self.schedule_start_var.get(),
            self.schedule_end_var.get(),
        )
        # Preserve partially edited fields during search/filter refresh.
        if self._schedule_loaded is None or edited_schedule == self._schedule_loaded:
            self.schedule_enabled_var.set(overview.schedule_enabled)
            self.schedule_start_var.set(overview.schedule_start)
            self.schedule_end_var.set(overview.schedule_end)
            self._schedule_loaded = actual_schedule
        visible = filter_children(overview.children, self.search_var.get())
        self.total_var.set(str(overview.total_children))
        self.enrolled_var.set(
            f"{overview.recognized_children} de {overview.total_children}"
        )
        self.remaining_var.set(screen_time_label(overview.remaining_seconds))
        self.schedule_var.set(overview.schedule_text)
        self.result_counter.set(
            f"{len(visible)} de {overview.total_children} exibidos"
        )
        if overview.outside_schedule:
            self.schedule_var.set("Fora do horário")

        shared = Path("C:/ProgramData/FaceKids/criancas.sqlite3")
        is_shared = self.db_path.resolve() == shared.resolve()
        self.data_source_var.set(
            "Dados compartilhados do FaceKids • horários e saldos de hoje"
            if is_shared else
            "Atenção: banco local de teste. Ele pode não ser o mesmo da conta Filhos. "
            "Não utilize estes saldos como controle de segurança."
        )

        if not visible:
            box = tk.Frame(self.cards_frame, bg=BG_CARD, padx=30, pady=30)
            box.pack(fill=tk.X, pady=16)
            title = (
                "Nenhum filho cadastrado"
                if not overview.children else
                "Nenhum filho corresponde à sua busca"
            )
            tk.Label(box, text=title, bg=BG_CARD, fg=TEXT_TITLE,
                     font=("Segoe UI", 13, "bold")).pack(pady=(0, 6))
            tk.Label(box, text=(
                "Clique em '+ Nova Criança' para criar um perfil."
                if not overview.children else
                "Altere o termo de busca para mostrar outros perfis."
            ), bg=BG_CARD, fg=TEXT_SUB,
                     font=("Segoe UI", 10)).pack()
            return

        for child in visible:
            self._create_child_card(
                child_id=child.child_id,
                name=child.name,
                samples=child.samples,
                limit_min=child.limit_minutes,
                used_sec=child.used_seconds,
                bonus_sec=child.bonus_minutes * 60,
                rem_sec=child.remaining_seconds,
            )

        self.cards_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

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

        if samples == 0:
            status_text, status_color = "○ Cadastro facial pendente", ACCENT_YELLOW
        elif rem_sec <= 0:
            status_text, status_color = "● Tempo esgotado hoje", ACCENT_RED
        else:
            status_text, status_color = f"● Rosto cadastrado · {samples} amostras", ACCENT_GREEN
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
                avatar_lbl = tk.Label(avatar_col, image=img, bg=BG_CARD, cursor="hand2")
                avatar_lbl.pack()
                avatar_lbl.bind("<Button-1>", lambda e, cid=child_id, cname=name: self._change_profile_photo(cid, cname))
            except Exception:
                self._draw_fallback_avatar(avatar_col, name, child_id)
        else:
            self._draw_fallback_avatar(avatar_col, name, child_id)

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

        change_lbl = tk.Label(
            avatar_col,
            text="Foto do Perfil\n(clique para mudar)",
            font=("Segoe UI", 8),
            fg=ACCENT_BLUE,
            bg=BG_CARD,
            justify="center",
            cursor="hand2",
        )
        change_lbl.pack(pady=(5, 0))
        change_lbl.bind("<Button-1>", lambda e, cid=child_id, cname=name: self._change_profile_photo(cid, cname))

        # A foto visual e a biometria sao controles independentes.
        photo_btn_row = tk.Frame(info_col, bg=BG_CARD)
        photo_btn_row.pack(fill=tk.X, pady=(4, 12))

        pick_file_btn = tk.Button(
            photo_btn_row,
            text="🖼️ Escolher Foto (Arquivo)",
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

        cam_photo_btn = tk.Button(
            photo_btn_row,
            text="📸 Tirar Foto (Webcam)",
            font=("Segoe UI", 9, "bold"),
            bg=BG_BOX,
            fg=ACCENT_BLUE,
            activebackground=BG_BOX_HOVER,
            activeforeground=ACCENT_BLUE,
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=5,
            command=lambda cid=child_id, cname=name: self._capture_photo_webcam(cid, cname),
        )
        cam_photo_btn.pack(side=tk.LEFT, padx=(0, 8))

        webcam_btn = tk.Button(
            photo_btn_row,
            text="👤 Cadastrar Biometria",
            font=("Segoe UI", 9),
            bg=BG_BOX,
            fg=TEXT_TITLE,
            activebackground=BG_BOX_HOVER,
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
        bar_canvas = tk.Canvas(quota_box, height=6, bg=BG_FIELD, highlightthickness=0)
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
                bg=ACCENT_BLUE if limit_min == m else BG_FIELD,
                fg=TEXT_ON_ACCENT if limit_min == m else TEXT_TITLE,
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
            bg=BG_FIELD,
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
                bg=BG_FIELD,
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
            bg=BG_FIELD,
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
            fg=TEXT_ON_ACCENT,
            activebackground=YELLOW_HOVER,
            activeforeground=TEXT_ON_ACCENT,
            relief=tk.FLAT,
            cursor="hand2",
            padx=6,
            pady=1,
            command=_apply_custom_bonus,
        )
        apply_btn.pack(side=tk.LEFT, padx=1)
        bonus_entry.bind("<Return>", lambda e: _apply_custom_bonus())

    def _draw_fallback_avatar(self, parent, name: str, child_id: Optional[int] = None):
        """Desenha avatar circular placeholder com a inicial quando nao ha foto."""
        canvas = tk.Canvas(parent, width=100, height=100, bg=BG_CARD, highlightthickness=0, cursor="hand2" if child_id else "")
        canvas.pack()
        canvas.create_oval(6, 6, 94, 94, fill=BG_BOX, outline=ACCENT_BLUE, width=2)
        initial = name[0].upper() if name else "F"
        canvas.create_text(50, 50, text=initial, font=("Segoe UI", 32, "bold"), fill=ACCENT_CYAN)
        if child_id is not None:
            canvas.bind("<Button-1>", lambda e, cid=child_id, cname=name: self._change_profile_photo(cid, cname))

    def _change_profile_photo(self, child_id: int, child_name: str):
        """Exibe menu para o usuario escolher a foto do perfil por arquivo ou webcam."""
        dialog = tk.Toplevel(self)
        dialog.title(f"Foto do Perfil — {child_name}")
        dialog.configure(bg=BG_CARD)
        dialog.geometry("380x210")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        tk.Label(
            dialog,
            text=f"Foto do Perfil: {child_name}",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_TITLE,
            bg=BG_CARD,
        ).pack(pady=(16, 4))

        tk.Label(
            dialog,
            text="Esta foto representará o perfil no painel e na tela de desbloqueio.",
            font=("Segoe UI", 9),
            fg=TEXT_SUB,
            bg=BG_CARD,
        ).pack(pady=(0, 16))

        btn_box = tk.Frame(dialog, bg=BG_CARD)
        btn_box.pack(fill=tk.X, padx=24)

        def _pick_file():
            dialog.destroy()
            self._pick_photo_file(child_id)

        def _pick_cam():
            dialog.destroy()
            self._capture_photo_webcam(child_id, child_name)

        tk.Button(
            btn_box,
            text="📁  Escolher Arquivo do Computador",
            font=("Segoe UI", 9, "bold"),
            bg=BG_BOX,
            fg=ACCENT_CYAN,
            activebackground=BG_BOX_HOVER,
            relief=tk.FLAT,
            cursor="hand2",
            pady=7,
            command=_pick_file,
        ).pack(fill=tk.X, pady=(0, 8))

        tk.Button(
            btn_box,
            text="📸  Tirar Foto Agora com a Webcam",
            font=("Segoe UI", 9, "bold"),
            bg=BG_BOX,
            fg=ACCENT_BLUE,
            activebackground=BG_BOX_HOVER,
            relief=tk.FLAT,
            cursor="hand2",
            pady=7,
            command=_pick_cam,
        ).pack(fill=tk.X)

    def _capture_photo_webcam(self, child_id: int, child_name: str):
        """Abre janela com visualização da webcam para capturar a foto oficial do perfil."""
        try:
            import cv2
        except ImportError:
            messagebox.showerror("Erro", "OpenCV não está disponível.", parent=self)
            return

        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW if sys.platform == "win32" else 0)
        if not cap.isOpened():
            cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("Câmera Indisponível", "Não foi possível acessar a webcam. Verifique se outro aplicativo está usando a câmera.", parent=self)
            return

        win = tk.Toplevel(self)
        win.title(f"Tirar Foto do Perfil — {child_name}")
        win.configure(bg=BG_MAIN)
        win.geometry("540x530")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        header = tk.Frame(win, bg=BG_MAIN)
        header.pack(fill=tk.X, padx=16, pady=(12, 6))
        tk.Label(
            header,
            text=f"📷 Foto do Perfil: {child_name}",
            font=("Segoe UI", 13, "bold"),
            fg=TEXT_TITLE,
            bg=BG_MAIN,
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Centralize o rosto no círculo e clique em 'Capturar Foto' (ou aperte Espaço).",
            font=("Segoe UI", 9),
            fg=TEXT_SUB,
            bg=BG_MAIN,
        ).pack(anchor="w", pady=(2, 0))

        preview_canvas = tk.Canvas(win, width=480, height=360, bg="#0B0B12", highlightthickness=1, highlightbackground=BORDER_CARD)
        preview_canvas.pack(pady=8)

        btn_bar = tk.Frame(win, bg=BG_MAIN)
        btn_bar.pack(fill=tk.X, padx=28, pady=(8, 12))

        is_running = [True]
        current_frame = [None]
        photo_ref = [None]

        def _close():
            is_running[0] = False
            try:
                cap.release()
            except Exception:
                pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _close)

        def _capture():
            if current_frame[0] is None:
                return
            frame = current_frame[0].copy()
            _close()

            self.status_text.set(f"Processando foto capturada para {child_name}...")
            self.update_idletasks()

            face_box = None
            if MODELS_DIR.exists():
                try:
                    from .recognition import Recognizer
                    rec = Recognizer(MODELS_DIR)
                    faces = rec.faces(frame)
                    if len(faces) >= 1:
                        face_box = max(faces, key=lambda f: float(f[2]) * float(f[3]))
                except Exception:
                    pass

            png_path = save_child_photo(child_id, frame, face_box, store=self.store)
            if png_path and png_path.exists():
                messagebox.showinfo("Foto Atualizada", f"Foto do perfil de {child_name} atualizada com sucesso!\nEsta mesma foto aparecerá no painel e na tela de boas-vindas.", parent=self)
                self.status_text.set(f"Foto do perfil de {child_name} atualizada com sucesso!")
            else:
                messagebox.showerror("Aviso", "Falha ao salvar foto do perfil.", parent=self)
                self.status_text.set("Falha ao salvar foto.")

            self.refresh()

        capture_btn = tk.Button(
            btn_bar,
            text="📸  Capturar Foto",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT_BLUE,
            fg="#0B0B12",
            activebackground=ACCENT_CYAN,
            activeforeground="#0B0B12",
            relief=tk.FLAT,
            cursor="hand2",
            padx=16,
            pady=6,
            command=_capture,
        )
        capture_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        cancel_btn = tk.Button(
            btn_bar,
            text="✕ Cancelar",
            font=("Segoe UI", 10),
            bg=BG_BOX,
            fg=TEXT_TITLE,
            activebackground=BG_BOX_HOVER,
            relief=tk.FLAT,
            cursor="hand2",
            padx=14,
            pady=6,
            command=_close,
        )
        cancel_btn.pack(side=tk.RIGHT)

        win.bind("<space>", lambda e: _capture())
        win.bind("<Return>", lambda e: _capture())
        win.bind("<Escape>", lambda e: _close())

        def _update_feed():
            if not is_running[0]:
                return
            ok, frame = cap.read()
            if ok and frame is not None:
                frame = cv2.flip(frame, 1)
                current_frame[0] = frame
                disp = cv2.resize(frame, (480, 360))
                cv2.circle(disp, (240, 180), 110, (240, 180, 56), 2, cv2.LINE_AA)
                rgb = cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)
                ok_enc, buf = cv2.imencode(".ppm", rgb)
                if ok_enc:
                    photo_ref[0] = tk.PhotoImage(data=buf.tobytes())
                    preview_canvas.delete("all")
                    preview_canvas.create_image(0, 0, anchor="nw", image=photo_ref[0])

            if is_running[0]:
                win.after(33, _update_feed)

        _update_feed()

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

        python_exe = sys.executable
        if python_exe.endswith("pythonw.exe"):
            py_normal = Path(python_exe).with_name("python.exe")
            if py_normal.exists():
                python_exe = str(py_normal)

        # Executa children_pilot enroll <id>
        cmd = [
            python_exe,
            "-m",
            "facekids.children_pilot",
            "--database",
            str(self.db_path),
            "enroll",
            str(child_id),
        ]
        try:
            self.active_enrollment_proc = subprocess.Popen(cmd, cwd=str(ROOT_DIR))
            self.status_text.set(f"Janela de captura da webcam aberta para o Perfil #{child_id}...")

            # Thread para aguardar termino e atualizar UI
            def _wait_completion():
                exit_code = self.active_enrollment_proc.wait()
                self.after(500, self._on_enrollment_finished, child_id, exit_code)

            threading.Thread(target=_wait_completion, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Erro ao Iniciar Webcam", f"Não foi possível iniciar o cadastro: {e}", parent=self)

    def _on_enrollment_finished(self, child_id: int, exit_code: int = 0):
        if exit_code == 0:
            self.status_text.set(f"Cadastro via webcam finalizado com sucesso para o Perfil #{child_id}.")
        elif exit_code == 2:
            self.status_text.set(f"Cadastro via webcam cancelado para o Perfil #{child_id}.")
        else:
            self.status_text.set(f"Falha no cadastro via webcam (código {exit_code}).")
            messagebox.showerror(
                "Falha no Cadastro",
                f"O processo de cadastro da webcam encerrou com erro (código {exit_code}).\n"
                "Verifique se a câmera não está em uso por outro aplicativo.",
                parent=self,
            )
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
