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
from typing import Optional, Tuple

if sys.platform == "win32":
    from ctypes import wintypes
else:
    wintypes = None

from .children_pilot import child_pilot_database
from .locker import lock_current_session
from .platform_paths import application_data_dir
from .session import SessionState, current_session_state
from .storage import Storage
from .quota_agent_accounting import LegacyLedgerQuota
from .unlock_event import validated_unlock_event, enrolled_display_name
from .ipc_json import parse_local_json
from .ipc_reply import validated_face_observation
from .windows_pipe_api import configure_kernel32
from .session_transition_policy import decide_child_transition, TransitionDecision
from .quota_vm_shadow_integration import VmBoundShadow, shadow_enabled_for_vm

AUTH_PIPE_NAME = os.environ.get("FACEKIDS_AUTH_PIPE", r"\\.\pipe\FaceKidsAuthPipe")

log_dir = application_data_dir()
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

LAST_UNLOCK_FILE = application_data_dir() / "last_unlock.json"
CONFIG_SETTINGS_FILE = application_data_dir() / "configuracoes.json"
DEFAULT_INACTIVITY_LOCK_SECONDS = 120.0  # 2 minutos de inatividade sem teclado/mouse
DEFAULT_INACTIVITY_WARN_SECONDS = 100.0  # Aviso aos 1m40s
DEFAULT_FACE_CHECK_INTERVAL_SECONDS = 120.0  # Verificacao facial periodica a cada 2 minutos


def get_inactivity_settings() -> Tuple[float, float]:
    """Retorna (lock_seconds, warn_seconds) a partir de configuracoes.json ou padroes do sistema."""
    lock_sec = DEFAULT_INACTIVITY_LOCK_SECONDS
    warn_sec = DEFAULT_INACTIVITY_WARN_SECONDS
    if CONFIG_SETTINGS_FILE.exists():
        try:
            data = json.loads(CONFIG_SETTINGS_FILE.read_text(encoding="utf-8"))
            if "inactivity_lock_seconds" in data:
                lock_sec = float(data["inactivity_lock_seconds"])
            if "inactivity_warn_seconds" in data:
                warn_sec = float(data["inactivity_warn_seconds"])
            else:
                warn_sec = max(10.0, lock_sec - 20.0)
        except Exception:
            pass
    return max(30.0, lock_sec), max(10.0, warn_sec)


def get_face_check_interval() -> float:
    """Retorna o intervalo em segundos para a verificacao facial periodica em sessao."""
    interval = DEFAULT_FACE_CHECK_INTERVAL_SECONDS
    if CONFIG_SETTINGS_FILE.exists():
        try:
            data = json.loads(CONFIG_SETTINGS_FILE.read_text(encoding="utf-8"))
            if "face_check_interval_seconds" in data:
                interval = float(data["face_check_interval_seconds"])
        except Exception:
            pass
    return max(15.0, interval)


def get_user_idle_seconds() -> float:
    """Retorna quantos segundos a sessao esta sem interacao fisica de mouse ou teclado."""
    if sys.platform != "win32":
        return 0.0
    try:
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        user32 = getattr(getattr(ctypes, "windll", None), "user32", None)
        kernel32 = getattr(getattr(ctypes, "windll", None), "kernel32", None)
        if user32 and kernel32 and hasattr(user32, "GetLastInputInfo"):
            if user32.GetLastInputInfo(ctypes.byref(lii)):
                millis = kernel32.GetTickCount() - lii.dwTime
                return max(0.0, millis / 1000.0)
    except Exception:
        pass
    return 0.0


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
    """Verifica se a janela de boas-vindas gerenciada por este agente ainda esta ativa."""
    global _welcome_proc
    with _welcome_lock:
        return _welcome_proc is not None and _welcome_proc.poll() is None


_welcome_proc: Optional[subprocess.Popen] = None
_welcome_lock = threading.Lock()


def dismiss_welcome_screen():
    """Encerra qualquer janela de boas-vindas aberta se o PC for bloqueado."""
    global _welcome_proc
    with _welcome_lock:
        if _welcome_proc is not None:
            try:
                if _welcome_proc.poll() is None:
                    _welcome_proc.terminate()
                    try:
                        _welcome_proc.wait(timeout=0.6)
                    except Exception:
                        _welcome_proc.kill()
            except Exception as e:
                logger.debug("Erro ao encerrar welcome_screen anterior: %s", e)
            _welcome_proc = None


def trigger_welcome_screen():
    """Dispara a tela de boas-vindas no Desktop da conta Filhos (apenas 1 instancia)."""
    global _welcome_proc
    if is_welcome_screen_running():
        logger.info("Tela de boas-vindas ja esta aberta; atualizacao ocorrera via evento local.")
        return

    logger.info("Disparando tela de boas-vindas no Desktop dos Filhos...")
    dismiss_welcome_screen()
    try:
        root_dir = Path(__file__).resolve().parent.parent
        pyw = root_dir / ".venv" / "Scripts" / "pythonw.exe"
        if not pyw.exists():
            pyw = Path(sys.executable)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(root_dir)
        with _welcome_lock:
            _welcome_proc = subprocess.Popen(
                [str(pyw), "-m", "facekids.welcome_screen"],
                cwd=str(root_dir),
                env=env,
            )
        logger.info("Tela de boas-vindas iniciada com sucesso (PID %d).", _welcome_proc.pid)
    except Exception as e:
        logger.error("Erro ao iniciar tela de boas-vindas: %s", e)


def query_auth_service(timeout_seconds: float = 2.0, pipe_name: Optional[str] = None, *, command: str = "AUTH_QUERY") -> Optional[dict]:
    """Consulta o servico facial com um prazo total, inclusive para ReadFile.

    O handle e aberto com I/O sobreposto para que uma resposta travada nunca
    mantenha indefinidamente a thread de identificacao da sessao.
    """
    if sys.platform != "win32":
        return None
    kernel32 = getattr(getattr(ctypes, "windll", None), "kernel32", None)
    if kernel32 is None:
        return None
    if pipe_name is None:
        pipe_name = AUTH_PIPE_NAME

    configure_kernel32(kernel32)

    deadline = time.monotonic() + max(0.1, float(timeout_seconds))

    def remaining_ms() -> int:
        return max(0, int((deadline - time.monotonic()) * 1000))

    if hasattr(kernel32, "WaitNamedPipeW"):
        wait_ms = min(300, remaining_ms())
        if wait_ms <= 0 or not kernel32.WaitNamedPipeW(pipe_name, wait_ms):
            return None

    file_flag_overlapped = 0x40000000
    h_pipe = kernel32.CreateFileW(
        pipe_name,
        0xC0000000,
        0,
        None,
        3,
        file_flag_overlapped,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if not h_pipe or h_pipe == invalid_handle:
        return None
    try:
        class OVERLAPPED(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_void_p),
                ("InternalHigh", ctypes.c_void_p),
                ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE),
            ]

        error_io_pending = 997
        wait_object_0 = 0

        def perform_io(function, buffer, size: int, transferred) -> bool:
            event = kernel32.CreateEventW(None, True, False, None)
            if not event:
                return False
            overlapped = OVERLAPPED()
            overlapped.hEvent = event
            try:
                ok = function(
                    h_pipe,
                    buffer,
                    size,
                    ctypes.byref(transferred),
                    ctypes.byref(overlapped),
                )
                if ok:
                    return True
                if kernel32.GetLastError() != error_io_pending:
                    return False

                wait_ms = remaining_ms()
                if wait_ms <= 0 or kernel32.WaitForSingleObject(event, wait_ms) != wait_object_0:
                    if hasattr(kernel32, "CancelIoEx"):
                        kernel32.CancelIoEx(h_pipe, ctypes.byref(overlapped))
                    else:
                        kernel32.CancelIo(h_pipe)
                    # OVERLAPPED e evento devem permanecer validos ate o SO
                    # concluir o cancelamento. CancelIoEx faz a operacao sair
                    # com ERROR_OPERATION_ABORTED e sinalizar o evento.
                    kernel32.GetOverlappedResult(
                        h_pipe,
                        ctypes.byref(overlapped),
                        ctypes.byref(transferred),
                        True,
                    )
                    return False
                return bool(
                    kernel32.GetOverlappedResult(
                        h_pipe,
                        ctypes.byref(overlapped),
                        ctypes.byref(transferred),
                        False,
                    )
                )
            finally:
                kernel32.CloseHandle(event)

        if command not in ("AUTH_QUERY", "SESSION_QUERY"):
            raise ValueError("Invalid local face command")
        payload = (command + "\n").encode("ascii")
        req = ctypes.create_string_buffer(payload)
        written = wintypes.DWORD()
        if not perform_io(kernel32.WriteFile, req, len(payload), written):
            return None

        buf = ctypes.create_string_buffer(2048)
        bytes_read = wintypes.DWORD()
        ok = perform_io(kernel32.ReadFile, buf, 2047, bytes_read)
        if ok and bytes_read.value > 0:
            resp_str = buf.raw[:bytes_read.value].decode("utf-8", errors="strict").strip()
            return parse_local_json(resp_str)
    except Exception as e:
        logger.debug("Falha na consulta ao pipe em sessao: %s", e)
    finally:
        kernel32.CloseHandle(h_pipe)
    return None


class InSessionFaceIdentifier:
    """Realiza consultas assincronas ao servico facial sem bloquear o loop de quota."""

    def __init__(self, interval_seconds: float = 15.0):
        self.interval = interval_seconds
        self.last_query_mono = 0.0
        self.thread: Optional[threading.Thread] = None
        self.pending_result: Optional[dict] = None
        self._lock = threading.Lock()

    def check_result(self) -> Optional[dict]:
        with self._lock:
            res = self.pending_result
            self.pending_result = None
            return res

    def trigger_if_due(self):
        now = time.monotonic()
        if (now - self.last_query_mono) < self.interval:
            return
        if self.thread and self.thread.is_alive():
            return

        self.last_query_mono = now

        def _worker():
            # O reconhecimento facial pode usar ate 4,5 s; 6,5 s inclui
            # conexao e transporte sem jamais bloquear o loop principal.
            res = query_auth_service(timeout_seconds=6.5, command="SESSION_QUERY")
            with self._lock:
                self.pending_result = res

        self.thread = threading.Thread(target=_worker, daemon=True)
        self.thread.start()


def read_last_unlock_child() -> Tuple[Optional[int], str, float]:
    """Le as informacoes do ultimo filho identificado se recente e de hoje."""
    if LAST_UNLOCK_FILE.exists():
        try:
            data = parse_local_json(LAST_UNLOCK_FILE.read_text(encoding="utf-8"))
            validated = validated_unlock_event(data)
            if validated is not None:
                return validated
        except Exception as e:
            logger.warning("Erro ao ler last_unlock.json: %s", e)
    return None, "", 0.0


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
        # WTSUserName = 5
        ok = wts.WTSQuerySessionInformationW(0, active_sid, 5, ctypes.byref(buf), ctypes.byref(bytes_read))
        if not ok or not buf.value:
            return False
        username = ctypes.wstring_at(buf.value).strip().lower()
        wts.WTSFreeMemory(buf)
        return username == "filhos"
    except Exception:
        return os.environ.get("USERNAME", "").lower() == "filhos"

def run_agent():
    # Garante que o agente so roda se a sessao ativa for a conta Filhos
    if not is_active_console_user_filhos():
        logger.info("FilhosAgent: Sessao de console ativa nao pertence a 'Filhos' (usuario: %s). Encerrando imediatamente.", os.environ.get("USERNAME"))
        return

    # Evita multiplas instancias concorrentes na mesma sessao
    kernel32 = ctypes.windll.kernel32
    h_mutex = kernel32.CreateMutexW(None, False, "Local\\FaceKidsFilhosAgentMutex")
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        logger.info("Outra instancia de FilhosAgent ja esta em execucao nesta sessao. Encerrando duplicata.")
        return

    logger.info("Iniciando FilhosAgent na conta %s (PID %d)...", os.environ.get("USERNAME", "Filhos"), os.getpid())

    db_path = child_pilot_database()
    store = Storage(db_path)
    quota_accounting = LegacyLedgerQuota(store)  # Still the only family writer.
    tracker = QuotaTracker(store)
    shadow_probe = VmBoundShadow() if shadow_enabled_for_vm() else None
    if shadow_probe is not None:
        logger.warning("VM shadow-only enabled; no broker writes, locks, or logon decisions")

    # last_unlock.json is UI-only: never assign quota owner from writable JSON.
    cid, cname, unlock_ts = read_last_unlock_child()
    last_seen_ts = unlock_ts if cid is not None else time.time()
    tracker.current_child_id = None
    tracker.current_child_name = "Nao identificado"
    if cid is not None and (time.time() - unlock_ts) < 15:
        trigger_welcome_screen()
    else:
        show_toast(
            "FaceControl Kids",
            "Olhe para a webcam para carregar seu tempo de tela.",
            icon="👤", color="#89DCEB", duration_ms=6000)

    last_active_time = time.monotonic()
    session_active_since_mono = time.monotonic()
    check_interval = get_face_check_interval()
    identifier = InSessionFaceIdentifier(interval_seconds=check_interval)
    today = date.today().isoformat()
    inactivity_warned = False
    previous_session_state = None

    logger.info("Monitoramento ativo iniciado. Criança ativa inicial: %s (ID %s)", tracker.current_child_name, tracker.current_child_id)

    # 2. Loop continuo de monitoramento (a cada 2 segundos)
    while True:
        try:
            if not is_active_console_user_filhos():
                # Administrador no console ativo (ex: troca rapida de usuario)
                time.sleep(2.0)
                continue

            now_day = date.today().isoformat()
            if now_day != today:
                today = now_day
                tracker.reset_warnings()

            # Notification file is UI-only. It must not change identity or
            # restart the inactivity clock (a Filhos process can edit it).
            if LAST_UNLOCK_FILE.exists():
                try:
                    event = validated_unlock_event(
                        parse_local_json(LAST_UNLOCK_FILE.read_text(encoding="utf-8")))
                    if event is not None and event[2] > last_seen_ts:
                        last_seen_ts = event[2]
                        if (time.time() - event[2] < 15.0 and
                                current_session_state() is SessionState.ACTIVE):
                            trigger_welcome_screen()
                except (OSError, ValueError, TypeError) as e:
                    logger.debug("Evento UI ignorado: %s", e)

            # B. Checar se a sessao esta ativa ou bloqueada
            state = current_session_state()
            if state is SessionState.LOCKED:
                dismiss_welcome_screen()
            if state is SessionState.ACTIVE and previous_session_state is not SessionState.ACTIVE:
                session_active_since_mono = time.monotonic()
                last_active_time = time.monotonic()
                identifier.last_query_mono = 0.0
            previous_session_state = state

            if state is SessionState.ACTIVE:
                # 1. Checar inatividade fisica considerando o tempo real desde que a sessao destravou
                active_duration = max(0.0, time.monotonic() - session_active_since_mono)
                idle_sec = min(get_user_idle_seconds(), active_duration)
                lock_sec, warn_sec = get_inactivity_settings()

                # C. Verificacao facial periodica em sessao ativa
                pipe_resp = identifier.check_result()
                if pipe_resp:
                    status = pipe_resp.get("status")
                    data_block = pipe_resp.get("data", {})
                    observed = validated_face_observation(pipe_resp)
                    if observed is not None:
                        registered_name = enrolled_display_name(store, observed.child_id)
                        if registered_name is None:
                            logger.warning("Observacao ignorada: perfil nao cadastrado.")
                        else:
                            transition = decide_child_transition(
                                tracker.current_child_id, list(observed.detected_ids),
                                observed.face_count, idle_sec, observed.child_id,
                                observation_age_seconds=max(0.0, time.time() - observed.timestamp))
                            if observed.status == "ALLOW":
                                if transition is TransitionDecision.SWITCH_CHILD:
                                    logger.info("Troca de perfil validada: %s -> %s",
                                                tracker.current_child_name, registered_name)
                                    tracker.switch_child(observed.child_id, registered_name)
                                    session_active_since_mono = time.monotonic()
                                    trigger_welcome_screen()
                                    show_toast("👋 Perfil Alternado",
                                               f"Olá, {registered_name}! Seu perfil foi carregado.",
                                               icon="👤", color="#A6E3A1", duration_ms=6000)
                            elif (observed.status in ("DENY_QUOTA", "DENY_CURFEW")
                                  and tracker.current_child_id is not None
                                  and transition is TransitionDecision.SWITCH_CHILD):
                                logger.warning("Perfil diferente sem quota/horario: %s", registered_name)
                                show_toast("🔒 FaceControl Kids",
                                           f"{registered_name}: acesso indisponivel. O computador sera bloqueado.",
                                           icon="🔒", color="#F38BA8")
                                time.sleep(1.2)
                                lock_current_session()
                    elif status in ("ALLOW", "DENY_QUOTA", "DENY_CURFEW"):
                        logger.warning("Decisao facial ignorada: resposta inconsistente ou antiga")

                # Agenda a proxima checagem facial
                identifier.trigger_if_due()

                # Checar se horario de dormir / curfew esta ativo
                is_curfew, curfew_msg = store.is_curfew_active()
                if is_curfew:
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
                    session_active_since_mono = time.monotonic()
                    continue

                # Checar inatividade fisica (teclado e mouse)
                if idle_sec >= lock_sec:
                    logger.info("Inatividade de %.1fs detectada (limite %.0fs). Bloqueando sessao...", idle_sec, lock_sec)
                    # Reembolsa o tempo de inatividade para a crianca nao perder saldo
                    if tracker.current_child_id is not None and idle_sec > 0:
                        refund = min(idle_sec, lock_sec)
                        store.refund(tracker.current_child_id, refund, today)
                        rem = store.remaining(tracker.current_child_id, today)
                        tracker.update_balance(rem)
                        logger.info("Reembolsados %.0fs de inatividade para %s. Saldo ajustado: %.0fs", refund, tracker.current_child_name, rem)
                    try:
                        lock_current_session()
                    except Exception as e:
                        logger.error("Erro ao solicitar bloqueio por inatividade: %s", e)
                    inactivity_warned = False
                    session_active_since_mono = time.monotonic()
                    time.sleep(3.0)
                    last_active_time = time.monotonic()
                    continue
                elif idle_sec >= warn_sec and not inactivity_warned:
                    inactivity_warned = True
                    logger.info("Aviso de inatividade: %.1fs sem interacao", idle_sec)
                    show_toast(
                        "⚠️ Ausência Detectada",
                        "Mexa o mouse ou teclado para continuar usando o computador.",
                        icon="🖱️",
                        color="#F9E2AF",
                        duration_ms=8000,
                    )
                elif idle_sec < warn_sec:
                    inactivity_warned = False

                now_mono = time.monotonic()
                delta = now_mono - last_active_time
                last_active_time = now_mono

                # Se o delta for razoavel (entre 0.5s e 15s, evitando picos apos hibernacao)
                if tracker.current_child_id is not None and 0.5 <= delta <= 15.0:
                    tick = quota_accounting.active_tick(
                        child_id=tracker.current_child_id, seconds=delta, day=today)
                    rem = tick.remaining_seconds
                    tracker.update_balance(rem)

                    # Shadow may observe this child, but NEVER change rem,
                    # trigger a lock, or select a facial identity.
                    if shadow_probe is not None:
                        try:
                            shadow_probe.trigger_if_due(
                                child_id=tracker.current_child_id, day=today,
                                remaining_seconds=rem)
                        except Exception as shadow_error:
                            logger.debug("Shadow diagnostic unavailable: %s",
                                         type(shadow_error).__name__)

                    # Verifica avisos e bloqueio automatico
                    locked = tracker.check_notifications_and_lock(rem) if tick.may_enforce_lock else False
                    if locked:
                        # Se bloqueou, aguarda um pouco para estabilizar o lock
                        time.sleep(5.0)
                        last_active_time = time.monotonic()
                        session_active_since_mono = time.monotonic()
                if shadow_probe is not None:
                    # Diagnostic-only: reads a service-bound child ID from the
                    # OS-verified VM pipe, never asserts identity or authority.
                    try:
                        local_rem = (store.remaining(tracker.current_child_id, today)
                                     if tracker.current_child_id is not None else 0.0)
                        comparison = shadow_probe.take_result(
                            current_child_id=tracker.current_child_id,
                            current_day=today, current_remaining=local_rem)
                        if comparison is not None:
                            logger.info("VM shadow-only: %s; delta_seconds=%s; age=%.2f",
                                        comparison.outcome,
                                        comparison.difference_seconds,
                                        comparison.sample_age_seconds)
                    except Exception as shadow_error:
                        logger.debug("Shadow read failed non-fatally: %s",
                                     type(shadow_error).__name__)
            else:
                # Sessao bloqueada (Win+L) ou suspensa: NAO cobra tempo!
                last_active_time = time.monotonic()
                session_active_since_mono = time.monotonic()

        except Exception as e:
            logger.error("Erro no loop de rastreamento do FilhosAgent: %s", e)

        time.sleep(2.0)


if __name__ == "__main__":
    run_agent()
