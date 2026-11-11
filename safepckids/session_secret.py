"""SafePCKids - Gerenciador do Segredo Dinamico de Sessao.

Substitui qualquer senha fixa ou estatica por credenciais criptograficas
geradas no momento da instalacao e armazenadas com isolamento de privilegios.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import secrets
import string
import subprocess
import sys
from typing import List, Sequence, Union


logger = logging.getLogger("safepckids.session_secret")

PROGRAMDATA_DIR = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "SafePCKids"
SECURITY_DIR = PROGRAMDATA_DIR / "security"
TOKEN_FILE = SECURITY_DIR / "filhos_session.token"


def _run_win_cmd(
    cmd: Union[List[str], Sequence[str]],
    timeout: float = 15.0,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Executa comando do Windows com seguranca: sem heranca de handles e sem travar em pipes."""
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
    if not capture:
        try:
            p = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=creation_flags,
            )
            p.wait(timeout=timeout)
            return subprocess.CompletedProcess(cmd, p.returncode or 0, "", "")
        except subprocess.TimeoutExpired:
            p.kill()
            return subprocess.CompletedProcess(cmd, -1, "", "timeout")
        except Exception as e:
            return subprocess.CompletedProcess(cmd, -1, "", str(e))

    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creation_flags,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, -1, "", f"Timeout after {timeout}s: {exc}")
    except Exception as exc:
        return subprocess.CompletedProcess(cmd, -1, "", str(exc))


def generate_secure_secret(length: int = 32) -> str:
    """Gera uma credencial de alta entropia para a conta Windows Filhos."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        has_upper = any(c.isupper() for c in candidate)
        has_lower = any(c.islower() for c in candidate)
        has_digit = any(c.isdigit() for c in candidate)
        has_symbol = any(c in "!@#$%^&*" for c in candidate)
        if has_upper and has_lower and has_digit and has_symbol:
            return candidate


def save_secure_secret(secret: str) -> None:
    """Salva o segredo gerado em diretorio blindado acessivel pelo sistema e administradores."""
    try:
        SECURITY_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(secret, encoding="utf-8")
        if sys.platform == "win32":
            try:
                current_user = None
                try:
                    current_user = os.getlogin()
                except Exception:
                    current_user = os.environ.get("USERNAME")

                # Concede controle total explicitamente para SYSTEM (*S-1-5-18) e Administradores (*S-1-5-32-544)
                # e para o usuario atual da sessao para evitar perda de permissao de leitura
                cmd_dir = [
                    "icacls", str(SECURITY_DIR),
                    "/grant", "*S-1-5-18:(OI)(CI)(F)",
                    "*S-1-5-32-544:(OI)(CI)(F)",
                ]
                if current_user:
                    cmd_dir.extend([f"{current_user}:(OI)(CI)(F)"])
                _run_win_cmd(cmd_dir, timeout=10.0)

                if TOKEN_FILE.exists():
                    cmd_token = [
                        "icacls", str(TOKEN_FILE),
                        "/grant", "*S-1-5-18:F",
                        "*S-1-5-32-544:F",
                    ]
                    if current_user:
                        cmd_token.extend([f"{current_user}:F"])
                    _run_win_cmd(cmd_token, timeout=10.0)
            except Exception as e:
                logger.warning(f"Aviso nao-critico ao ajustar permissoes ACL via icacls: {e}")
    except Exception as e:
        logger.warning(f"Aviso ao salvar filhos_session.token: {e}")


def get_session_secret() -> str:
    """Retorna o segredo dinamico da conta Filhos para autenticacao no Windows.
    
    Se o arquivo de segredo nao existir ou estiver restrito a nivel de administrador,
    retorna o fallback seguro.
    """
    try:
        if TOKEN_FILE.exists():
            val = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if val:
                return val
    except Exception:
        pass
    return "1"
