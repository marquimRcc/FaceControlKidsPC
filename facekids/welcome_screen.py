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
import subprocess
import sys
import time
import tkinter as tk
from datetime import date
from pathlib import Path
from typing import Optional

from .avatar_utils import get_child_avatar_path
from .children_pilot import child_pilot_database
from .platform_paths import application_data_dir
from .storage import Storage

CONFIG_FILE = application_data_dir() / "programas_inicializar.json"
LAST_UNLOCK_FILE = application_data_dir() / "last_unlock.json"

logger = logging.getLogger("FaceKidsWelcome")


def is_process_running_in_current_session(exe_name: str) -> bool:
    """Verifica se um processo com o nome do executavel esta ativo NA MESMA SESSAO do Windows."""
    if not exe_name:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32

            my_pid = kernel32.GetCurrentProcessId()
            my_session = wintypes.DWORD()
            if not kernel32.ProcessIdToSessionId(my_pid, ctypes.byref(my_session)):
                return False

            TH32CS_SNAPPROCESS = 0x00000002

            class PROCESSENTRY32W(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes.DWORD),
                    ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260),
                ]

            h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if h_snap == ctypes.c_void_p(-1).value:
                return False
            try:
                pe = PROCESSENTRY32W()
                pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                if not kernel32.Process32FirstW(h_snap, ctypes.byref(pe)):
                    return False
                target = exe_name.lower()
                proc_session = wintypes.DWORD()
                while True:
                    if pe.szExeFile.lower() == target:
                        if kernel32.ProcessIdToSessionId(pe.th32ProcessID, ctypes.byref(proc_session)):
                            if proc_session.value == my_session.value:
                                return True
                    if not kernel32.Process32NextW(h_snap, ctypes.byref(pe)):
                        break
                return False
            finally:
                kernel32.CloseHandle(h_snap)
        except Exception:
            return False
    else:
        try:
            target = exe_name.lower()
            for pid_dir in Path("/proc").glob("[0-9]*"):
                comm_file = pid_dir / "comm"
                if comm_file.exists() and comm_file.read_text().strip().lower() == target:
                    return True
        except Exception:
            pass
        return False


def default_programs_config() -> dict:
    return {
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


def load_programs_config() -> dict:
    default_config = default_programs_config()
    if not CONFIG_FILE.exists():
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(default_config, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return default_config

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        changed = False
        for prog in data.get("programs", []):
            if "youtubekids.com" in prog.get("arguments", "").lower():
                prog["arguments"] = ""
                if "youtube" in prog.get("name", "").lower():
                    prog["name"] = "Brave"
                changed = True
        if changed:
            try:
                CONFIG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        return data
    except Exception:
        return default_config


_programs_launched = False



def is_active_console_user_filhos() -> bool:
    """Verifica se a sessao de console fisica ativa pertence de fato a conta 'Filhos'."""
    override = os.environ.get("FACEKIDS_TEST_ACTIVE_USER")
    if override:
        return override.lower() == "filhos"
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        from ctypes import wintypes
        wts = ctypes.windll.wtsapi32
        kernel32 = ctypes.windll.kernel32
        active_sid = kernel32.WTSGetActiveConsoleSessionId()
        buf = ctypes.c_void_p()
        bytes_read = wintypes.DWORD()
        ok = wts.WTSQuerySessionInformationW(0, active_sid, 5, ctypes.byref(buf), ctypes.byref(bytes_read))
        if not ok or not buf.value:
            return False
        username = ctypes.wstring_at(buf.value).strip().lower()
        wts.WTSFreeMemory(buf)
        return username == "filhos"
    except Exception:
        return os.environ.get("USERNAME", "").lower() == "filhos"

def launch_configured_programs():
    if not is_active_console_user_filhos():
        logger.info("Programas configurados nao serao executados fora da sessao de console dos Filhos.")
        return

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
        if not Path(exe).is_file():
            logger.warning("Programa configurado nao encontrado: %s", exe)
            continue
        exe_name = Path(exe).name
        if is_process_running_in_current_session(exe_name):
            logger.info("Programa '%s' ja esta em execucao na sessao atual. Nenhuma nova aba/janela sera aberta.", exe_name)
            continue
        try:
            import shlex
            cmd = [exe]
            if args:
                cmd.extend(shlex.split(args))
            subprocess.Popen(cmd, shell=False)
            logger.info("Programa iniciado com sucesso: %s", exe)
        except Exception as e:
            logger.warning("Falha ao iniciar programa '%s': %s", exe, e)


def get_current_child_info() -> tuple[Optional[int], str, int]:
    """Recupera id, nome e saldo restante em segundos do ultimo desbloqueio autenticado.
    Retorna None no id se nao houver desbloqueio recente valido.
    """
    if LAST_UNLOCK_FILE.exists():
        try:
            data = json.loads(LAST_UNLOCK_FILE.read_text(encoding="utf-8"))
            ts = float(data.get("timestamp", 0))
            is_fresh = True
            if ts > 0:
                if (time.time() - ts) >= 600:
                    is_fresh = False
                elif date.fromtimestamp(ts).isoformat() != date.today().isoformat():
                    is_fresh = False

            cid = data.get("child_id")
            if is_fresh and cid is not None:
                cid = int(cid)
                name = data.get("child_name", f"Crianca {cid}")
                try:
                    db = child_pilot_database()
                    if db.exists():
                        store = Storage(db)
                        today = date.today().isoformat()
                        rem = int(store.remaining(cid, today))
                        store.close()
                        return cid, name, rem
                except Exception:
                    pass
                rem = int(data.get("remaining_seconds", 0))
                return cid, name, rem
        except Exception:
            pass

    return None, "Filho(a)", 0


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
        self._last_seen_ts = time.time()

        # Posicionamento para arrastar janela
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Configuracao da janela
        self.root.title("FaceControl Kids")
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.bind("<Map>", self._on_map)

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
        # 420px preserva a dica inferior em escalas de tela do Windows acima
        # de 100%, sem apertar o card de quota ou o botao principal.
        height = 420
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

        # Barra superior com botoes [—] minimizar e [✕] fechar
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

        min_btn = tk.Button(
            header_bar,
            text="—",
            font=("Segoe UI", 9, "bold"),
            fg=self.text_sub,
            bg=self.bg_card,
            activeforeground="#FFFFFF",
            activebackground="#313244",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.minimize,
            bd=0,
            padx=8,
            pady=1,
        )
        min_btn.pack(side=tk.RIGHT, padx=(0, 4))

        # 1. Avatar da Crianca
        self.avatar_frame = tk.Frame(container, bg=self.bg_card)
        self.avatar_frame.pack(pady=(10, 6))
        self._render_avatar()

        # 2. Titulo e Saudacao
        salutation = f"Olá, {self.child_name}! 👋" if self.child_id is not None else "Olá! 👋"
        self.title_label = tk.Label(
            container,
            text=salutation,
            font=("Segoe UI", 18, "bold"),
            fg=self.text_title,
            bg=self.bg_card,
        )
        self.title_label.pack(pady=(4, 2))

        sub_msg = "Desbloqueio facial realizado com sucesso!" if self.child_id is not None else "Entrada por PIN ou aguardando identificação facial."
        self.sub_label = tk.Label(
            container,
            text=sub_msg,
            font=("Segoe UI", 10),
            fg=self.text_sub,
            bg=self.bg_card,
        )
        self.sub_label.pack(pady=(0, 14))

        # 3. Card de Tempo Restante
        quota_box = tk.Frame(container, bg=self.bg_box, highlightbackground="#313244", highlightthickness=1)
        quota_box.pack(fill=tk.X, padx=32, pady=(0, 16))

        if self.child_id is not None:
            time_str = format_remaining_time(self.remaining_seconds)
            time_icon_text = f"⏱️  Tempo disponível hoje: {time_str}"
        else:
            time_icon_text = "⏱️  Aguardando identificação facial..."

        self.time_icon_label = tk.Label(
            quota_box,
            text=time_icon_text,
            font=("Segoe UI", 11, "bold"),
            fg=self.accent_cyan,
            bg=self.bg_box,
        )
        self.time_icon_label.pack(pady=(10, 6))

        self.bar_canvas = tk.Canvas(quota_box, width=320, height=8, bg=self.bar_bg, highlightthickness=0)
        self.bar_canvas.pack(pady=(0, 10))
        self._update_quota_bar()

        # 4. Botao de Acao Principal
        btn_frame = tk.Frame(container, bg=self.bg_card)
        btn_frame.pack(fill=tk.X, padx=32)

        start_btn = tk.Button(
            btn_frame,
            text="✓  OK, Entendi",
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

        # 5. Dica de uso informativa (o tempo ja esta contando)
        self.hint_label = tk.Label(
            container,
            text="⏱️ Seu tempo já começou a contar! Esta janela pode ser minimizada a qualquer momento.",
            font=("Segoe UI", 9),
            fg=self.text_sub,
            bg=self.bg_card,
        )
        self.hint_label.pack(pady=(8, 10))

        # Mantem em primeiro plano (topmost) por 30 segundos; apos isso aceita segundo plano
        self._topmost_job = self.root.after(30000, self._drop_topmost)
        self._tick_countdown()

    def minimize(self):
        """Minimiza a janela para a barra de tarefas do Windows."""
        try:
            self.root.update_idletasks()
            self.root.overrideredirect(False)
            self.root.iconify()
        except Exception as e:
            logger.debug("Erro ao minimizar janela: %s", e)

    def _on_map(self, event):
        """Restaura borderless quando a janela for desminimizada."""
        try:
            if self.root.state() == "normal" and not self.root.overrideredirect():
                self.root.overrideredirect(True)
        except Exception:
            pass

    def _drop_topmost(self):
        """Apos 30 segundos, deixa de forcar a janela sobre o navegador."""
        try:
            self.root.attributes("-topmost", False)
            logger.info("Topmost desativado apos 30 segundos; janela agora aceita segundo plano.")
        except Exception:
            pass

    def _render_avatar(self):
        """Renderiza o avatar circular da foto oficial da crianca ou o fallback de inicial."""
        if not hasattr(self, "avatar_frame") or not self.avatar_frame.winfo_exists():
            return
        for child in self.avatar_frame.winfo_children():
            child.destroy()

        avatar_path = get_child_avatar_path(self.child_id) if self.child_id is not None else None
        loaded = False
        if avatar_path and avatar_path.exists():
            try:
                self.photo_image = tk.PhotoImage(file=str(avatar_path))
                avatar_label = tk.Label(self.avatar_frame, image=self.photo_image, bg=self.bg_card)
                avatar_label.pack()
                loaded = True
            except Exception as e:
                logger.warning("Falha ao carregar imagem do avatar %s: %s", avatar_path, e)

        if not loaded:
            self._draw_fallback_avatar(self.avatar_frame)

    def _update_quota_bar(self):
        """Atualiza a barra visual de progresso da quota da crianca."""
        if not hasattr(self, "bar_canvas") or not self.bar_canvas.winfo_exists():
            return
        self.bar_canvas.delete("all")
        total_seconds = 7200
        pct = max(0.0, min(1.0, self.remaining_seconds / total_seconds)) if self.child_id is not None else 0.0
        fill_width = int(320 * pct)
        if fill_width > 0:
            bar_color = self.bar_fill if pct > 0.25 else "#F38BA8"
            self.bar_canvas.create_rectangle(0, 0, fill_width, 8, fill=bar_color, width=0)

    def _check_for_child_switch(self):
        """Detecta em tempo real se outra crianca desbloqueou o PC e atualiza a interface."""
        if not LAST_UNLOCK_FILE.exists():
            return
        try:
            data = json.loads(LAST_UNLOCK_FILE.read_text(encoding="utf-8"))
            current_ts = float(data.get("timestamp", 0.0))
            if current_ts > self._last_seen_ts:
                self._last_seen_ts = current_ts
                new_cid = data.get("child_id")
                new_cname = data.get("child_name")
                new_rem = int(data.get("remaining_seconds", 0))
                if new_cid is not None and (new_cid != self.child_id or new_cname != self.child_name):
                    logger.info("Outra crianca reconhecida no lockscreen: %s (ID %s). Atualizando tela...", new_cname, new_cid)
                    self.switch_child(new_cid, str(new_cname), new_rem)
        except Exception as e:
            logger.debug("Erro ao checar troca de crianca: %s", e)

    def switch_child(self, new_child_id: int, new_child_name: str, new_remaining_seconds: int):
        """Atualiza a tela de boas-vindas para uma nova crianca identificada sem recriar a janela."""
        self.child_id = new_child_id
        self.child_name = new_child_name
        self.remaining_seconds = new_remaining_seconds

        if hasattr(self, "title_label") and self.title_label.winfo_exists():
            self.title_label.config(text=f"Olá, {self.child_name}! 👋")
        if hasattr(self, "sub_label") and self.sub_label.winfo_exists():
            self.sub_label.config(text="Desbloqueio facial realizado com sucesso!")
        if hasattr(self, "time_icon_label") and self.time_icon_label.winfo_exists():
            self.time_icon_label.config(text=f"⏱️  Tempo disponível hoje: {format_remaining_time(self.remaining_seconds)}")

        self._update_quota_bar()
        self._render_avatar()

        # Restaura da minimizacao e reativa topmost por 30s para a nova crianca
        try:
            if self.root.state() != "normal":
                self.root.overrideredirect(True)
                self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.lift()
            if hasattr(self, "_topmost_job") and self._topmost_job:
                try:
                    self.root.after_cancel(self._topmost_job)
                except Exception:
                    pass
            self._topmost_job = self.root.after(30000, self._drop_topmost)
        except Exception as e:
            logger.debug("Erro ao restaurar janela no switch_child: %s", e)

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

    def _tick_countdown(self):
        self._check_for_child_switch()
        if self.child_id is not None and self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            time_str = format_remaining_time(self.remaining_seconds)
            try:
                if hasattr(self, "time_icon_label") and self.time_icon_label.winfo_exists():
                    self.time_icon_label.config(text=f"⏱️  Tempo disponível hoje: {time_str}")
            except Exception:
                pass
        try:
            self._timer_job = self.root.after(1000, self._tick_countdown)
        except Exception:
            pass

    def dismiss(self):
        if hasattr(self, "_topmost_job") and self._topmost_job:
            try:
                self.root.after_cancel(self._topmost_job)
            except Exception:
                pass
            self._topmost_job = None
        if hasattr(self, "_timer_job") and self._timer_job:
            try:
                self.root.after_cancel(self._timer_job)
            except Exception:
                pass
            self._timer_job = None
        try:
            self.root.destroy()
        except Exception:
            pass
        # Inicializa programas configurados
        launch_configured_programs()


def show_welcome():
    if not is_active_console_user_filhos():
        if sys.platform == "win32" and not os.environ.get("FACEKIDS_TEST_ACTIVE_USER"):
            for _ in range(4):
                time.sleep(0.5)
                if is_active_console_user_filhos():
                    break
            else:
                logger.info("Tela de boas-vindas ignorada: sessao de console ativa nao e 'Filhos'.")
                return
        else:
            logger.info("Tela de boas-vindas ignorada: sessao de console ativa nao e 'Filhos'.")
            return

    # Mutex de sessao para impedir janelas sobrepostas
    h_mutex = None
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            h_mutex = kernel32.CreateMutexW(None, False, "Local\\FaceKidsWelcomeScreenWindow")
            if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                logger.info("Outra janela de boas-vindas ja esta aberta nesta sessao; encerrando instancia duplicada.")
                return
        except Exception:
            pass

    try:
        child_id, child_name, remaining_seconds = get_current_child_info()
        # Abre o conteudo infantil apenas depois de um reconhecimento facial valido.
        # A janela de boas-vindas permanece topmost e aparece sobre o navegador.
        if child_id is not None:
            launch_configured_programs()
        root = tk.Tk()
        app = WelcomeWindow(root, child_id, child_name, remaining_seconds)
        root.mainloop()
    finally:
        if h_mutex and sys.platform == "win32":
            try:
                kernel32.CloseHandle(h_mutex)
            except Exception:
                pass


if __name__ == "__main__":
    show_welcome()
