"""FaceControlKidsPC - Watchdog de Protecao Anti-Burla do Agente da conta Filhos.

Monitora a sessao ativa do Windows quando conectada na conta 'Filhos'.
Se o processo filhos_agent.py for finalizado (ou cair) enquanto a sessao
estiver desbloqueada (ACTIVE), o watchdog tenta relanca-lo via Agendador de
Tarefas (FaceKidsFilhosAgent). Apos falhas consecutivas sem recuperacao,
executa o bloqueio preventivo da sessao para impedir uso ilimitado sem quota.
"""
from __future__ import annotations

import ctypes
from enum import Enum
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Callable, Optional, Tuple

if sys.platform == "win32":
    from ctypes import wintypes
else:
    wintypes = None

from .platform_paths import application_data_dir
from .session import SessionState, current_session_state

logger = logging.getLogger("FaceKidsAgentWatchdog")


class WatchdogAction(str, Enum):
    NO_ACTION = "no_action"
    GRACE_PERIOD = "grace_period"
    HEARTBEAT_OK = "heartbeat_ok"
    RECOVERY_TRIGGERED = "recovery_triggered"
    PREVENTIVE_LOCK = "preventive_lock"


def heartbeat_file_path() -> Path:
    return application_data_dir() / "agent_heartbeat.json"


def write_agent_heartbeat(path: Optional[Path] = None) -> bool:
    """Grava atomicamente o timestamp e PID do agente no arquivo de heartbeat."""
    target_path = path or heartbeat_file_path()
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = target_path.with_suffix(".tmp")
        data = {
            "timestamp": time.time(),
            "pid": os.getpid(),
            "version": "1.0",
        }
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(target_path)
        return True
    except Exception as e:
        logger.debug("Falha ao gravar heartbeat do agente: %s", e)
        return False


def read_agent_heartbeat(path: Optional[Path] = None) -> Tuple[Optional[float], Optional[int]]:
    """Retorna (timestamp, pid) lidos do arquivo de heartbeat, se valido."""
    target_path = path or heartbeat_file_path()
    if not target_path.exists():
        return None, None
    try:
        content = target_path.read_text(encoding="utf-8")
        data = json.loads(content)
        ts = float(data.get("timestamp", 0.0))
        pid = int(data.get("pid", 0)) if "pid" in data else None
        return ts, pid
    except Exception as e:
        logger.debug("Erro ao ler heartbeat do agente: %s", e)
        return None, None


def get_active_console_session_id() -> int:
    """Retorna o ID da sessao do console ativo no Windows (WTSGetActiveConsoleSessionId)."""
    if os.name != "nt":
        return 0xFFFFFFFF
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        return int(kernel32.WTSGetActiveConsoleSessionId())
    except Exception:
        return 0xFFFFFFFF


def get_session_username(session_id: int) -> Optional[str]:
    """Retorna o nome de usuario autenticado na sessao especificada (WTSUserName)."""
    if os.name != "nt" or session_id == 0xFFFFFFFF or wintypes is None:
        return None
    wts = ctypes.WinDLL("wtsapi32", use_last_error=True)
    buf = ctypes.c_void_p()
    num_bytes = wintypes.DWORD()
    WTS_USER_NAME = 5
    try:
        ok = wts.WTSQuerySessionInformationW(
            None, session_id, WTS_USER_NAME, ctypes.byref(buf), ctypes.byref(num_bytes)
        )
        if ok and buf.value:
            return ctypes.wstring_at(buf)
        return None
    except Exception:
        return None
    finally:
        if buf.value:
            wts.WTSFreeMemory(buf)


def default_trigger_recovery(task_name: str = "FaceKidsFilhosAgent") -> bool:
    """Dispara a tarefa agendada FaceKidsFilhosAgent no Windows."""
    try:
        creation_flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        res = subprocess.run(
            ["schtasks.exe", "/run", "/tn", task_name],
            capture_output=True,
            timeout=5.0,
            creationflags=creation_flags,
        )
        return res.returncode == 0
    except Exception as e:
        logger.warning("Falha ao disparar tarefa de recuperacao %s: %s", task_name, e)
        return False


def default_lock_session(session_id: Optional[int] = None) -> bool:
    """Bloqueia a sessao ativa do Windows."""
    try:
        if session_id is not None and sys.platform == "win32":
            wts = ctypes.WinDLL("wtsapi32", use_last_error=True)
            if hasattr(wts, "WTSDisconnectSession"):
                wts.WTSDisconnectSession(None, session_id, False)
                return True
        if sys.platform == "win32":
            return bool(ctypes.windll.user32.LockWorkStation())
        return False
    except Exception as e:
        logger.error("Falha ao bloquear estacao: %s", e)
        return False


class AgentWatchdog:
    """Monitor de integridade e presenca do processo filhos_agent.py."""

    def __init__(
        self,
        *,
        heartbeat_max_age: float = 45.0,
        startup_grace_period: float = 60.0,
        target_user: str = "Filhos",
        heartbeat_file: Optional[Path] = None,
        task_name: str = "FaceKidsFilhosAgent",
        session_state_fn: Optional[Callable[[int], SessionState]] = None,
        session_user_fn: Optional[Callable[[int], Optional[str]]] = None,
        console_session_fn: Optional[Callable[[], int]] = None,
        recovery_fn: Optional[Callable[[], bool]] = None,
        lock_fn: Optional[Callable[[Optional[int]], bool]] = None,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        self.heartbeat_max_age = heartbeat_max_age
        self.startup_grace_period = startup_grace_period
        self.target_user = target_user
        self.heartbeat_file = heartbeat_file
        self.task_name = task_name

        self._session_state_fn = session_state_fn or current_session_state
        self._session_user_fn = session_user_fn or get_session_username
        self._console_session_fn = console_session_fn or get_active_console_session_id
        self._recovery_fn = recovery_fn or (lambda: default_trigger_recovery(self.task_name))
        self._lock_fn = lock_fn or default_lock_session
        self._time_fn = time_fn or time.time

        self.start_time = self._time_fn()
        self.grace_until = self.start_time + self.startup_grace_period
        self.consecutive_failures = 0

    def notify_allow(self, grace_seconds: Optional[float] = None):
        """Concede periodo de carencia adicional apos logon/desbloqueio bem-sucedido."""
        now = self._time_fn()
        grace = grace_seconds if grace_seconds is not None else max(60.0, self.startup_grace_period)
        self.grace_until = max(self.grace_until, now + grace)
        self.consecutive_failures = 0

    def check_once(self) -> WatchdogAction:
        """Executa uma verificacao do estado do agente na sessao ativa."""
        now = self._time_fn()
        sid = self._console_session_fn()
        if sid == 0xFFFFFFFF:
            return WatchdogAction.NO_ACTION

        active_user = self._session_user_fn(sid)
        if not active_user or active_user.casefold() != self.target_user.casefold():
            # Usuario diferente da conta Filhos (ex.: MarcosMiniPC, SYSTEM) -> nao monitora
            self.consecutive_failures = 0
            return WatchdogAction.NO_ACTION

        state = self._session_state_fn(sid)
        if state is not SessionState.ACTIVE:
            # Sessao de Filhos esta bloqueada (Win+L) ou desconectada -> nao monitora
            self.consecutive_failures = 0
            return WatchdogAction.NO_ACTION

        if now < self.grace_until:
            return WatchdogAction.GRACE_PERIOD

        hb_time, _ = read_agent_heartbeat(self.heartbeat_file)
        if hb_time is not None:
            age = now - hb_time
            if 0 <= age <= self.heartbeat_max_age:
                self.consecutive_failures = 0
                return WatchdogAction.HEARTBEAT_OK

        # Heartbeat ausente ou expirado (> 45s) com sessao Filhos ACTIVE
        self.consecutive_failures += 1
        logger.warning(
            "Heartbeat do agente Filhos ausente ou expirado (falha %d/2).",
            self.consecutive_failures,
        )

        if self.consecutive_failures == 1:
            logger.info("Disparando tarefa de recuperacao do agente: %s", self.task_name)
            self._recovery_fn()
            return WatchdogAction.RECOVERY_TRIGGERED

        # 2 ou mais falhas consecutivas
        logger.warning(
            "Agente Filhos ausente/encerrado na sessao ativa; executando bloqueio preventivo"
        )
        self._lock_fn(sid)
        return WatchdogAction.PREVENTIVE_LOCK


class AgentWatchdogThread(threading.Thread):
    """Thread daemon de segundo plano para inspecao periodica."""

    def __init__(self, watchdog: AgentWatchdog, check_interval: float = 15.0):
        super().__init__(name="FaceKidsAgentWatchdogThread", daemon=True)
        self.watchdog = watchdog
        self.check_interval = check_interval
        self._stop_event = threading.Event()

    def run(self):
        logger.info("Iniciando AgentWatchdogThread (intervalo: %.1fs)...", self.check_interval)
        while not self._stop_event.is_set():
            try:
                self.watchdog.check_once()
            except Exception as e:
                logger.error("Erro inesperado no AgentWatchdog: %s", e)
            self._stop_event.wait(self.check_interval)

    def stop(self):
        self._stop_event.set()
