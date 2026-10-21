"""FaceControlKidsPC - Agente de Sessao da conta Filhos.

Roda silenciosamente em segundo plano na conta 'Filhos' (sessao interativa).
Funcoes:
1. Exibe a tela de boas-vindas imediatamente no primeiro login do Windows;
2. Monitora 'C:\\ProgramData\\FaceKids\\last_unlock.json' e reabre a tela de
   boas-vindas sempre que um desbloqueio facial for concluido na tela de bloqueio.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time

log_dir = Path("C:/ProgramData/FaceKids")
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "filhos_agent.log"

logging.basicConfig(
    filename=str(log_file),
    level=logging.INFO,
    format="[%(asctime)s] [FilhosAgent] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("FilhosAgent")

LAST_UNLOCK_FILE = Path("C:/ProgramData/FaceKids/last_unlock.json")


def is_welcome_screen_running() -> bool:
    """Verifica se ja existe uma janela de boas-vindas aberta para evitar duplicatas."""
    try:
        cmd = 'tasklist /fi "imagename eq pythonw.exe" /v /fo csv'
        output = subprocess.check_output(cmd, shell=True, text=True, errors="ignore")
        return "FaceControl Kids" in output or "welcome_screen" in output
    except Exception:
        return False


def trigger_welcome_screen():
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


def run_agent():
    logger.info("Iniciando FilhosAgent na conta %s (PID %d)...", os.environ.get("USERNAME", "Filhos"), os.getpid())

    # 1. Ao iniciar a sessao, exibe a tela de boas-vindas na hora
    time.sleep(1.0)
    trigger_welcome_screen()

    last_seen_ts = 0.0
    if LAST_UNLOCK_FILE.exists():
        try:
            data = json.loads(LAST_UNLOCK_FILE.read_text(encoding="utf-8"))
            last_seen_ts = float(data.get("timestamp", 0.0))
        except Exception:
            pass

    # 2. Loop de monitoramento de eventos de desbloqueio facial
    while True:
        try:
            if LAST_UNLOCK_FILE.exists():
                data = json.loads(LAST_UNLOCK_FILE.read_text(encoding="utf-8"))
                current_ts = float(data.get("timestamp", 0.0))
                if current_ts > last_seen_ts and (time.time() - current_ts) < 15.0:
                    last_seen_ts = current_ts
                    logger.info("Novo desbloqueio facial detectado para a crianca: %s", data.get("child_name"))
                    time.sleep(0.5)
                    trigger_welcome_screen()
        except Exception as e:
            logger.debug("Erro ao verificar unlock: %s", e)

        time.sleep(1.0)


if __name__ == "__main__":
    run_agent()
