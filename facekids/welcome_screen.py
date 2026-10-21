"""FaceControlKidsPC - Tela de Boas-Vindas e Quota do Filho.

Exibe um card moderno e amigavel logo apos o desbloqueio facial:
- Foto / Avatar do filho reconhecido
- Mensagem personalizada de boas-vindas
- Saldo de tempo restante hoje com barra visual
- Inicializacao opcional de programas configurados
- Permanece aberta ate o clique em 'Comecar Agora' ou no [X]
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk
from datetime import date
from typing import Optional

from .avatar_utils import get_child_avatar_path
from .storage import Storage
from .children_pilot import child_pilot_database

CONFIG_FILE = Path("C:/ProgramData/FaceKids/programas_inicializar.json")
LAST_UNLOCK_FILE = Path("C:/ProgramData/FaceKids/last_unlock.json")

logger = logging.getLogger("FaceKidsWelcome")


def load_programs_config() -> dict:
    default_config = {
        "enabled": True,
        "description": "Lista de programas a inicializar automaticamente apos o desbloqueio facial",
        "programs": [
            {
                "name": "Brave - YouTube Kids",
                "executable": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                "arguments": "https://www.youtubekids.com",
                "enabled": True,
            }
        ],
    }
    if not CONFIG_FILE.exists():
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return default_config

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return data
    except Exception:
        return default_config


_programs_launched = False


def launch_configured_programs():
    global _programs_launched
    if _programs_launched:
        return
    _programs_launched = True

    # Evita abrir programas na conta dos pais caso o administrador esteja apenas testando o visual
    current_user = os.environ.get("USERNAME", "")
    if current_user.casefold() == "marcosminipc":
        logger.info("Conta do administrador detectada: programas automaticos dos filhos nao serao abertos aqui.")
        return

    cfg = load_programs_config()
    if not cfg.get("enabled", False):
        return

    programs = cfg.get("programs", [])
    for prog in programs:
        if not prog.get("enabled", False):
            continue
        exe = prog.get("executable", "").strip()
        args = prog.get("arguments", "").strip()
        if not exe:
            continue
        try:
            cmd = f'"{exe}" {args}' if args else f'"{exe}"'
            subprocess.Popen(cmd, shell=True)
            logger.info("Programa iniciado com sucesso: %s", exe)
        except Exception as e:
            logger.warning("Falha ao iniciar programa '%s': %s", exe, e)


def get_current_child_info() -> tuple[int, str, int]:
    """Recupera id, nome e saldo restante em segundos do ultimo desbloqueio ou do banco."""
    # 1. Tentar ler do last_unlock.json se recente (menos de 10 minutos)
    if LAST_UNLOCK_FILE.exists():
        try:
            data = json.loads(LAST_UNLOCK_FILE.read_text(encoding="utf-8"))
            ts = data.get("timestamp", 0)
            if time.time() - ts < 600:
                cid = data.get("child_id", 2)
                name = data.get("child_name", f"Crianca {cid}")
                rem = data.get("remaining_seconds", 7200)
                return cid, name, rem
        except Exception:
            pass

    # 2. Consultar o banco SQLite
    try:
        db = child_pilot_database()
        if db.exists():
            store = Storage(db)
            today = date.today().isoformat()
            people = store.people()
            if people:
                # Padrao: Crianca 2 ou primeiro cadastrado
                target_pid = 2
                for pid, name, _ in people:
                    if pid == target_pid or len(people) == 1:
                        rem = int(store.remaining(pid, today))
                        store.close()
                        return pid, name, rem
            store.close()
    except Exception:
        pass

    return 2, "Filho(a)", 7200


def format_remaining_time(seconds: int) -> str:
    if seconds <= 0:
        return "Tempo esgotado para hoje"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0 and minutes > 0:
        return f"{hours}h {minutes:02d}min restantes"
    elif hours > 0:
        return f"{hours}h restantes"
    else:
        return f"{minutes} minutos restantes"


class WelcomeWindow:
    def __init__(self, root: tk.Tk, child_id: int, child_name: str, remaining_seconds: int):
        self.root = root
        self.child_id = child_id
        self.child_name = child_name
        self.remaining_seconds = remaining_seconds
        self.photo_image = None

        # Posicionamento para arrastar janela
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Configuracao da janela
        self.root.title("FaceControl Kids")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)

        # Cores modernas (Dark Card com detalhes Ciano/Azul)
        self.bg_card = "#181825"
        self.bg_box = "#1E1E2E"
        self.text_title = "#CDD6F4"
        self.text_sub = "#A6ADC8"
        self.accent_cyan = "#89DCEB"
        self.accent_blue = "#38BDF8"
        self.bar_bg = "#313244"
        self.bar_fill = "#A6E3A1"

        self.root.configure(bg="#0B0B12")

        # Centralizar na tela
        width = 460
        height = 380
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2 - 50
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        self._build_ui()

    def _build_ui(self):
        container = tk.Frame(self.root, bg=self.bg_card, highlightbackground=self.accent_blue, highlightthickness=2)
        container.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Permitir arrastar a janela
        container.bind("<Button-1>", self._start_drag)
        container.bind("<B1-Motion>", self._on_drag)

        # Barra superior com botao fechar [X]
        header_bar = tk.Frame(container, bg=self.bg_card)
        header_bar.pack(fill=tk.X, padx=12, pady=(8, 0))
        header_bar.bind("<Button-1>", self._start_drag)
        header_bar.bind("<B1-Motion>", self._on_drag)

        badge_label = tk.Label(
            header_bar,
            text="✨ FaceControl Kids",
            font=("Segoe UI", 9, "bold"),
            fg=self.accent_blue,
            bg=self.bg_card,
        )
        badge_label.pack(side=tk.LEFT)

        close_btn = tk.Button(
            header_bar,
            text="✕",
            font=("Segoe UI", 10, "bold"),
            fg=self.text_sub,
            bg=self.bg_card,
            activeforeground="#FFFFFF",
            activebackground="#E06C75",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.dismiss,
            bd=0,
            padx=8,
            pady=1,
        )
        close_btn.pack(side=tk.RIGHT)

        # 1. Avatar da Crianca
        avatar_frame = tk.Frame(container, bg=self.bg_card)
        avatar_frame.pack(pady=(10, 6))

        avatar_path = get_child_avatar_path(self.child_id)
        if avatar_path and avatar_path.exists():
            try:
                self.photo_image = tk.PhotoImage(file=str(avatar_path))
                avatar_label = tk.Label(avatar_frame, image=self.photo_image, bg=self.bg_card)
                avatar_label.pack()
            except Exception:
                self._draw_fallback_avatar(avatar_frame)
        else:
            self._draw_fallback_avatar(avatar_frame)

        # 2. Titulo e Saudacao
        title_label = tk.Label(
            container,
            text=f"Olá, {self.child_name}! 👋",
            font=("Segoe UI", 18, "bold"),
            fg=self.text_title,
            bg=self.bg_card,
        )
        title_label.pack(pady=(4, 2))

        sub_label = tk.Label(
            container,
            text="Desbloqueio facial realizado com sucesso!",
            font=("Segoe UI", 10),
            fg=self.text_sub,
            bg=self.bg_card,
        )
        sub_label.pack(pady=(0, 14))

        # 3. Card de Tempo Restante
        quota_box = tk.Frame(container, bg=self.bg_box, highlightbackground="#313244", highlightthickness=1)
        quota_box.pack(fill=tk.X, padx=32, pady=(0, 16))

        time_str = format_remaining_time(self.remaining_seconds)
        time_icon_label = tk.Label(
            quota_box,
            text=f"⏱️  Tempo disponível hoje: {time_str}",
            font=("Segoe UI", 11, "bold"),
            fg=self.accent_cyan,
            bg=self.bg_box,
        )
        time_icon_label.pack(pady=(10, 6))

        # Barra de progresso visual (quota base: 2h = 7200s)
        total_seconds = 7200
        pct = max(0.0, min(1.0, self.remaining_seconds / total_seconds))
        bar_canvas = tk.Canvas(quota_box, width=320, height=8, bg=self.bar_bg, highlightthickness=0)
        bar_canvas.pack(pady=(0, 10))
        fill_width = int(320 * pct)
        if fill_width > 0:
            bar_color = self.bar_fill if pct > 0.25 else "#F38BA8"
            bar_canvas.create_rectangle(0, 0, fill_width, 8, fill=bar_color, width=0)

        # 4. Botao de Acao Principal
        btn_frame = tk.Frame(container, bg=self.bg_card)
        btn_frame.pack(fill=tk.X, padx=32)

        start_btn = tk.Button(
            btn_frame,
            text="🚀  Começar Agora",
            font=("Segoe UI", 11, "bold"),
            bg=self.accent_blue,
            fg="#0B0B12",
            activebackground=self.accent_cyan,
            activeforeground="#0B0B12",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.dismiss,
            padx=16,
            pady=6,
        )
        start_btn.pack(fill=tk.X)

        # 5. Dica de uso
        hint_label = tk.Label(
            container,
            text="Clique em 'Começar Agora' ou no ✕ acima para usar o PC.",
            font=("Segoe UI", 9),
            fg=self.text_sub,
            bg=self.bg_card,
        )
        hint_label.pack(pady=(8, 10))

    def _start_drag(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_drag(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_start_x)
        y = self.root.winfo_y() + (event.y - self._drag_start_y)
        self.root.geometry(f"+{x}+{y}")

    def _draw_fallback_avatar(self, parent):
        canvas = tk.Canvas(parent, width=90, height=90, bg=self.bg_card, highlightthickness=0)
        canvas.pack()
        canvas.create_oval(5, 5, 85, 85, fill="#313244", outline=self.accent_blue, width=3)
        initial = self.child_name[0].upper() if self.child_name else "F"
        canvas.create_text(45, 45, text=initial, font=("Segoe UI", 32, "bold"), fill=self.accent_cyan)

    def dismiss(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        # Inicializa programas configurados
        launch_configured_programs()


def show_welcome():
    # Inicializa programas em segundo plano para ja estarem carregados quando o filho comecar
    launch_configured_programs()
    child_id, child_name, remaining_seconds = get_current_child_info()
    root = tk.Tk()
    app = WelcomeWindow(root, child_id, child_name, remaining_seconds)
    root.mainloop()


if __name__ == "__main__":
    show_welcome()
