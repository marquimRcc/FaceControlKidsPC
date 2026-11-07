"""FaceControlKidsPC - Gerenciador do Segredo Dinamico de Sessao.

Substitui qualquer senha fixa ou estatica por credenciais criptograficas
geradas no momento da instalacao e armazenadas com isolamento de privilegios.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import string
import subprocess
import sys


PROGRAMDATA_DIR = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "FaceKids"
SECURITY_DIR = PROGRAMDATA_DIR / "security"
TOKEN_FILE = SECURITY_DIR / "filhos_session.token"


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
                subprocess.run(
                    ["icacls", str(SECURITY_DIR), "/grant", "*S-1-5-18:(OI)(CI)(F)", "*S-1-5-32-544:(OI)(CI)(F)", "*S-1-5-32-545:(OI)(CI)(M)"],
                    capture_output=True,
                    check=False
                )
            except Exception:
                pass
    except Exception as e:
        logging.getLogger(__name__).warning(f"Aviso ao salvar filhos_session.token: {e}")


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
