"""FaceControlKidsPC - Agente de Sessao da conta Filhos.

Roda silenciosamente em segundo plano na conta 'Filhos' (sessao interativa).
Funcoes principais:
1. Exibe a tela de boas-vindas imediatamente no primeiro login do Windows e
   sempre que ocorrer um desbloqueio facial (monitorando last_unlock.json);
2. Rastreia o tempo de uso ativo da crianca em tempo real:
   - Desconta o tempo no banco SQLite compartilhado;
   - Pausa automaticamente quando o PC estiver bloqueado (Win+L) ou suspenso;
   - Emite avisos suaves e elegantes (toasts flutuantes) aos 10min, 5min e 1min restantes;
   - Bloqueia automaticamente o Windows (LockWorkStation) quando o tempo diário esgotar;
   - Ao bloquear, a tela de logon impede o retorno caso a quota esteja zerada.
"""
from __future__ import annotations

import ctypes
from datetime import date
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import tkinter as tk
from typing import Optional, Tuple

from .children_pilot import child_pilot_database
from .locker import lock_current_session
from .session import SessionState, current_session_state
from .storage import Storage

log_dir = Path("C:/ProgramData/FaceKids")
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "filhos_agent.log"

try:
    logging.basicConfig(
        filename=str(log_file),
        level=logging.INFO,
        format="[%(asctime)s] [FilhosAgent] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
except Exception:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [FilhosAgent] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
logger = logging.getLogger("FilhosAgent")

LAST_UNLOCK_FILE = Path("C:/ProgramData/FaceKids/last_unlock.json")


def show_toast(
    title: str,
    message: str,
    icon: str = "⏱️",
    color: str = "#38BDF8",
    duration_ms: int = 7000,
):
    """Exibe um toast flutuante e moderno no canto inferior direito da tela sem roubar foco."""
    def _run():
        try:
            toast = tk.Tk()
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            try:
                toast.attributes("-alpha", 0.95)
            except Exception:
                pass

            w, h = 390, 88
            screen_w = toast.winfo_screenwidth()
            screen_h = toast.winfo_screenheight()
            x = screen_w - w - 24
            y = screen_h - h - 50
            toast.geometry(f"{w}x{h}+{x}+{y}")
            toast.configure(bg="#181825")

            # Card container com borda destacada
            card = tk.Frame(
                toast,
                bg="#181825",
                highlightbackground=color,
                highlightthickness=2,
                padx=14,
                pady=10,
            )
            card.pack(fill=tk.BOTH, expand=True)

            # Icone
            lbl_icon = tk.Label(card, text=icon, font=("Segoe UI", 22), bg="#181825")
            lbl_icon.pack(side=tk.LEFT, padx=(0, 12))

            # Textos
            text_frame = tk.Frame(card, bg="#181825")
            text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            lbl_title = tk.Label(
                text_frame,
                text=title,
                font=("Segoe UI", 10, "bold"),
                fg=color,
                bg="#181825",
            )
            lbl_title.pack(anchor="w")

            lbl_msg = tk.Label(
                text_frame,
                text=message,
                font=("Segoe UI", 9),
                fg="#CDD6F4",
                bg="#181825",
                wraplength=280,
                justify="left",
            )
            lbl_msg.pack(anchor="w", pady=(2, 0))

            # Auto-destruicao apos a duracao especificada
            toast.after(duration_ms, toast.destroy)
            toast.mainloop()
        except Exception as e:
            logger.warning("Falha ao exibir toast: %s", e)

    threading.Thread(target=_run, daemon=True).start()


def is_welcome_screen_running() -> bool:
    """Verifica se ja existe uma janela de boas-vindas aberta para evitar duplicatas."""
    try:
        cmd = 'tasklist /fi "imagename eq pythonw.exe" /v /fo csv'
        output = subprocess.check_output(cmd, shell=True, text=True, errors="ignore")
        return "FaceControl Kids" in output or "welcome_screen" in output
    except Exception:
        return False


def trigger_welcome_screen():
    """Dispara a tela de boas-vindas no Desktop da conta Filhos."""
    logger.info("Disparando tela de boas-vindas no Desktop dos Filhos...")
    try:
        root_dir = Path(__file__).resolve().parent.parent
        pyw = root_dir / ".venv" / "Scripts" / "pythonw.exe"
        if not pyw.exists():
            pyw = Path(sys.executable)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(root_dir)
        subprocess.Popen(
            [str(pyw), "-m", "facekids.welcome_screen"],
            cwd=str(root_dir),
            env=env,
        )
        logger.info("Tela de boas-vindas iniciada com sucesso.")
    except Exception as e:
        logger.error("Erro ao iniciar tela de boas-vindas: %s", e)


def read_last_unlock_child() -> Tuple[Optional[int], str]:
    """Le as informacoes do ultimo filho identificado se recente e de hoje."""
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

            if is_fresh:
                cid = data.get("child_id")
                cname = data.get("child_name", f"Crianca {cid}")
                if cid is not None:
                    return int(cid), str(cname)
        except Exception as e:
            logger.warning("Erro ao ler last_unlock.json: %s", e)
    return None, ""


class QuotaTracker:
    """Gerenciador do saldo de tempo e notificacoes de aviso."""

    def __init__(self, store: Storage):
        self.store = store
        self.warned_10m = False
        self.warned_5m = False
        self.warned_1m = False
        self.current_child_id: Optional[int] = None
        self.current_child_name: str = ""

    def switch_child(self, child_id: int, child_name: str):
        if self.current_child_id != child_id:
            logger.info("Trocando rastreamento de crianca para ID %d (%s)", child_id, child_name)
            self.current_child_id = child_id
            self.current_child_name = child_name
            self.reset_warnings()

    def reset_warnings(self):
        self.warned_10m = False
        self.warned_5m = False
        self.warned_1m = False

    def update_balance(self, remaining: float):
        """Redefine os avisos caso o pai conceda bonus de tempo."""
        if remaining > 600:
            self.warned_10m = False
            self.warned_5m = False
            self.warned_1m = False
        elif remaining > 300:
            self.warned_5m = False
            self.warned_1m = False
        elif remaining > 60:
            self.warned_1m = False

    def check_notifications_and_lock(self, remaining: float) -> bool:
        """Verifica se deve emitir aviso ou bloquear a sessao. Retorna True se bloqueou."""
        name = self.current_child_name or "Filho"

        # 1. Quota esgotada (<= 0): Bloqueia imediatamente
        if remaining <= 0:
            logger.warning("Tempo esgotado para %s! Bloqueando sessao...", name)
            show_toast(
                "🔒 Tempo Esgotado",
                f"O tempo diário de uso do computador para {name} terminou. Até amanhã!",
                icon="🔒",
                color="#F38BA8",
                duration_ms=4000,
            )
            time.sleep(1.2)
            try:
                lock_current_session()
            except Exception as e:
                logger.error("Erro ao solicitar bloqueio do Windows: %s", e)
            self.reset_warnings()
            return True

        # 2. Aviso de 1 minuto
        if remaining <= 60 and not self.warned_1m:
            self.warned_1m = True
            logger.info("Emitindo aviso de 1 minuto para %s", name)
            show_toast(
                "🚨 Atenção: 1 Minuto Restante",
                f"Resta 1 minuto! O computador será bloqueado em instantes. Salve tudo agora!",
                icon="🛑",
                color="#F38BA8",
                duration_ms=8000,
            )

        # 3. Aviso de 5 minutos
        elif remaining <= 300 and not self.warned_5m:
            self.warned_5m = True
            logger.info("Emitindo aviso de 5 minutos para %s", name)
            show_toast(
                "⚠️ Atenção: 5 Minutos",
                f"Restam 5 minutos de tela hoje para {name}! Salve seus jogos e tarefas.",
                icon="⚠️",
                color="#F9E2AF",
                duration_ms=7000,
            )

        # 4. Aviso de 10 minutos
        elif remaining <= 600 and not self.warned_10m:
            self.warned_10m = True
            logger.info("Emitindo aviso de 10 minutos para %s", name)
            show_toast(
                "⏱️ FaceControl Kids",
                f"Olá, {name}! Restam 10 minutos de tempo de tela hoje.",
                icon="⏳",
                color="#89DCEB",
                duration_ms=6000,
            )

        return False


def run_agent():
    # Evita multiplas instancias concorrentes na mesma sessao
    kernel32 = ctypes.windll.kernel32
    h_mutex = kernel32.CreateMutexW(None, False, "Local\\FaceKidsFilhosAgentMutex")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        logger.info("Outra instancia de FilhosAgent ja esta em execucao nesta sessao. Encerrando duplicata.")
        return

    logger.info("Iniciando FilhosAgent na conta %s (PID %d)...", os.environ.get("USERNAME", "Filhos"), os.getpid())

    db_path = child_pilot_database()
    store = Storage(db_path)
    tracker = QuotaTracker(store)

    # 1. Exibe a tela de boas-vindas inicial no desktop
    time.sleep(1.0)
    trigger_welcome_screen()

    last_seen_ts = 0.0
    cid, cname = read_last_unlock_child()
    if cid is not None:
        tracker.switch_child(cid, cname)
    else:
        logger.info("Nenhum desbloqueio facial recente identificado. Sessao em modo aguardando identificacao facial.")
        tracker.current_child_id = None
        tracker.current_child_name = "Nao identificado" 

    last_active_time = time.monotonic()
    today = date.today().isoformat()

    logger.info("Monitoramento ativo iniciado. Criança ativa inicial: %s (ID %s)", tracker.current_child_name, tracker.current_child_id)

    # 2. Loop continuo de monitoramento (a cada 2 segundos)
    while True:
        try:
            now_day = date.today().isoformat()
            if now_day != today:
                today = now_day
                tracker.reset_warnings()

            # A. Verificar se houve novo evento de desbloqueio facial no lock screen
            if LAST_UNLOCK_FILE.exists():
                try:
                    data = json.loads(LAST_UNLOCK_FILE.read_text(encoding="utf-8"))
                    current_ts = float(data.get("timestamp", 0.0))
                    if current_ts > last_seen_ts:
                        last_seen_ts = current_ts
                        new_cid = data.get("child_id")
                        new_cname = data.get("child_name", f"Crianca {new_cid}")
                        if new_cid is not None:
                            tracker.switch_child(int(new_cid), str(new_cname))
                        # Se recente (menos de 15s), reabre a tela de boas-vindas
                        if (time.time() - current_ts) < 15.0:
                            logger.info("Novo desbloqueio facial detectado para: %s", new_cname)
                            time.sleep(0.5)
                            trigger_welcome_screen()
                except Exception as e:
                    logger.debug("Erro ao ler unlock timestamp: %s", e)

            # B. Checar se a sessao esta ativa ou bloqueada
            state = current_session_state()

            # Checar se horario de dormir / curfew esta ativo
            is_curfew, curfew_msg = store.is_curfew_active()
            if is_curfew and state is SessionState.ACTIVE:
                logger.warning("Horario de dormir ativo: %s. Bloqueando sessao...", curfew_msg)
                show_toast(
                    "🌙 Horário de Dormir",
                    f"{curfew_msg} O computador foi bloqueado. Até amanhã!",
                    icon="🌙",
                    color="#CBA6F7",
                    duration_ms=4500,
                )
                time.sleep(1.2)
                try:
                    lock_current_session()
                except Exception as e:
                    logger.error("Erro ao bloquear no horario de dormir: %s", e)
                time.sleep(5.0)
                last_active_time = time.monotonic()
                continue

            if state is SessionState.ACTIVE:
                now_mono = time.monotonic()
                delta = now_mono - last_active_time
                last_active_time = now_mono

                # Se o delta for razoavel (entre 0.5s e 15s, evitando picos apos hibernacao)
                if tracker.current_child_id is not None and 0.5 <= delta <= 15.0:
                    store.charge(tracker.current_child_id, delta, today)
                    rem = store.remaining(tracker.current_child_id, today)
                    tracker.update_balance(rem)

                    # Verifica avisos e bloqueio automatico
                    locked = tracker.check_notifications_and_lock(rem)
                    if locked:
                        # Se bloqueou, aguarda um pouco para estabilizar o lock
                        time.sleep(5.0)
                        last_active_time = time.monotonic()
            else:
                # Sessao bloqueada (Win+L) ou suspensa: NAO cobra tempo!
                last_active_time = time.monotonic()

        except Exception as e:
            logger.error("Erro no loop de rastreamento do FilhosAgent: %s", e)

        time.sleep(2.0)


if __name__ == "__main__":
    run_agent()
