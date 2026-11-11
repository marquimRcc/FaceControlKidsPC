"""SafePCKids - Cofre de Credenciais DPAPI do Windows.

Armazena a senha e usuario da conta Windows 'Filhos' de forma criptografada
via Windows DPAPI (CryptProtectData com CRYPTPROTECT_LOCAL_MACHINE), permitindo que
tanto a sessao administrativa dos pais quanto o processo SYSTEM (AuthService/LogonUI)
consigam autenticar o usuario automaticamente sem expor a senha em texto puro.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import logging
import os
from pathlib import Path
import sys
from typing import Optional, Tuple

from .session_secret import (
    PROGRAMDATA_DIR,
    SECURITY_DIR,
    TOKEN_FILE,
    _run_win_cmd,
    save_secure_secret,
)


logger = logging.getLogger("safepckids.credential_store")

CREDENTIALS_FILE = PROGRAMDATA_DIR / "credentials.bin"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_encrypt(data_bytes: bytes) -> bytes:
    """Criptografa bytes usando DPAPI no escopo LOCAL_MACHINE (0x4)."""
    if sys.platform != "win32":
        return data_bytes

    blob_in = DATA_BLOB(len(data_bytes), ctypes.cast(data_bytes, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    # 0x4 = CRYPTPROTECT_LOCAL_MACHINE
    crypt32 = getattr(getattr(ctypes, "windll", None), "crypt32", None)
    if not crypt32 or not crypt32.CryptProtectData(
        ctypes.byref(blob_in), "SafePCKidsCredentials", None, None, None, 0x4, ctypes.byref(blob_out)
    ):
        raise RuntimeError("Falha ao invocar CryptProtectData no Windows.")

    res = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return res


def _dpapi_decrypt(cipher_bytes: bytes) -> bytes:
    """Decriptografa bytes usando DPAPI."""
    if sys.platform != "win32":
        return cipher_bytes

    blob_in = DATA_BLOB(len(cipher_bytes), ctypes.cast(cipher_bytes, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    crypt32 = getattr(getattr(ctypes, "windll", None), "crypt32", None)
    if not crypt32 or not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise RuntimeError("Falha ao invocar CryptUnprotectData no Windows.")

    res = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return res


def save_filhos_credentials(username: str = "Filhos", password: str = "1") -> bool:
    """Grava as credenciais da conta Filhos criptografadas no cofre DPAPI e no token de sessao."""
    try:
        PROGRAMDATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"user": username, "password": password}).encode("utf-8")

        # 1. Criptografa via DPAPI
        try:
            encrypted = _dpapi_encrypt(payload)
            CREDENTIALS_FILE.write_bytes(encrypted)
        except Exception as e:
            logger.error(f"Nao foi possivel proteger a senha da conta Filhos via DPAPI: {e}")
            return False

        # 2. Ajusta permissoes ACL no arquivo de credenciais
        if sys.platform == "win32":
            try:
                current_user = None
                try:
                    current_user = os.getlogin()
                except Exception:
                    current_user = os.environ.get("USERNAME")

                cmd_acl = [
                    "icacls", str(CREDENTIALS_FILE),
                    "/grant", "*S-1-5-18:F",
                    "*S-1-5-32-544:F",
                ]
                if current_user:
                    cmd_acl.append(f"{current_user}:F")
                _run_win_cmd(cmd_acl, timeout=10.0)
            except Exception:
                pass

        # 3. Sincroniza com o arquivo de segredo legadado/compativel (TOKEN_FILE)
        save_secure_secret(password)
        logger.info(f"Credenciais da conta '{username}' gravadas com sucesso no cofre DPAPI.")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar credenciais da conta Filhos: {e}")
        return False


def get_filhos_credentials(*, default_password: str = "1") -> Tuple[str, str]:
    """Retorna (usuario, senha) a partir do cofre DPAPI, com fallback para TOKEN_FILE."""
    if CREDENTIALS_FILE.exists():
        try:
            data = CREDENTIALS_FILE.read_bytes()
            try:
                decrypted = _dpapi_decrypt(data)
            except Exception:
                decrypted = data
            info = json.loads(decrypted.decode("utf-8"))
            return str(info.get("user", "Filhos")), str(info.get("password", default_password))
        except Exception as e:
            logger.debug(f"Aviso ao ler credentials.bin: {e}")

    # Fallback para TOKEN_FILE
    if TOKEN_FILE.exists():
        try:
            val = TOKEN_FILE.read_text(encoding="utf-8").strip()
            if val:
                return "Filhos", val
        except Exception:
            pass

    return "Filhos", default_password


def get_filhos_password() -> str:
    """Retorna apenas a senha atual da conta Filhos."""
    _, password = get_filhos_credentials()
    return password
