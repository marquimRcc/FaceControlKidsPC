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
from pathlib import Path
import sys
from typing import Tuple

from .session_secret import (
    PROGRAMDATA_DIR,
    SECURITY_DIR,
    TOKEN_FILE,
    _run_win_cmd,
)


logger = logging.getLogger("safepckids.credential_store")

CREDENTIALS_FILE = SECURITY_DIR / "credentials.bin"
LEGACY_CREDENTIALS_FILE = PROGRAMDATA_DIR / "credentials.bin"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_encrypt(data_bytes: bytes) -> bytes:
    """Criptografa bytes usando DPAPI no escopo LOCAL_MACHINE (0x4)."""
    if sys.platform != "win32":
        raise RuntimeError("DPAPI esta disponivel somente no Windows.")

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
        raise RuntimeError("DPAPI esta disponivel somente no Windows.")

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


def _remove_legacy_secret() -> bool:
    try:
        TOKEN_FILE.unlink(missing_ok=True)
        return True
    except OSError as exc:
        logger.warning("Nao foi possivel remover o segredo legado em texto: %s", exc)
        return False


def _restrict_security_directory() -> None:
    if sys.platform != "win32":
        return
    result = _run_win_cmd([
        "icacls", str(SECURITY_DIR), "/inheritance:r", "/grant:r",
        "*S-1-5-18:(OI)(CI)(F)", "*S-1-5-32-544:(OI)(CI)(F)",
    ], timeout=10.0)
    if result.returncode != 0:
        raise RuntimeError(f"Falha ao restringir ACL do cofre: {result.stderr.strip()}")


def save_filhos_credentials(username: str, password: str) -> bool:
    """Grava credenciais exclusivamente no cofre DPAPI do Windows."""
    if not username or not password or password == "1":
        logger.error("Usuario e senha nao podem ser vazios nem usar a senha inicial insegura.")
        return False
    if not _remove_legacy_secret():
        return False

    staging_file = CREDENTIALS_FILE.with_suffix(CREDENTIALS_FILE.suffix + ".tmp")
    try:
        PROGRAMDATA_DIR.mkdir(parents=True, exist_ok=True)
        SECURITY_DIR.mkdir(parents=True, exist_ok=True)
        _restrict_security_directory()
        payload = json.dumps({"user": username, "password": password}).encode("utf-8")

        encrypted = _dpapi_encrypt(payload)
        staging_file.write_bytes(encrypted)
        staging_file.replace(CREDENTIALS_FILE)

        if sys.platform == "win32":
            acl = _run_win_cmd([
                "icacls", str(CREDENTIALS_FILE), "/inheritance:r", "/grant:r",
                "*S-1-5-18:F", "*S-1-5-32-544:F",
            ], timeout=10.0)
            if acl.returncode != 0:
                CREDENTIALS_FILE.unlink(missing_ok=True)
                raise RuntimeError(f"Falha ao restringir ACL de credentials.bin: {acl.stderr.strip()}")

        try:
            LEGACY_CREDENTIALS_FILE.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Nao foi possivel remover credentials.bin legado: %s", exc)
        logger.info(f"Credenciais da conta '{username}' gravadas com sucesso no cofre DPAPI.")
        return True
    except Exception as e:
        try:
            staging_file.unlink(missing_ok=True)
        except OSError as cleanup_error:
            logger.warning("Nao foi possivel remover o arquivo de staging DPAPI: %s", cleanup_error)
        logger.error(f"Erro ao salvar credenciais da conta Filhos: {e}")
        return False


def get_filhos_credentials() -> Tuple[str, str]:
    """Retorna credenciais DPAPI; segredos legados nunca sao usados como fallback."""
    _remove_legacy_secret()
    for path in (CREDENTIALS_FILE, LEGACY_CREDENTIALS_FILE):
        if not path.exists():
            continue
        try:
            encrypted = path.read_bytes()
            info = json.loads(_dpapi_decrypt(encrypted).decode("utf-8"))
            username = str(info.get("user", ""))
            password = str(info.get("password", ""))
            if username and password:
                if path == LEGACY_CREDENTIALS_FILE and password != "1":
                    if not save_filhos_credentials(username, password):
                        return "Filhos", ""
                elif path == LEGACY_CREDENTIALS_FILE:
                    logger.warning("Credencial inicial '1' requer rotacao antes de autenticar.")
                else:
                    try:
                        LEGACY_CREDENTIALS_FILE.unlink(missing_ok=True)
                    except OSError as exc:
                        logger.warning("Nao foi possivel remover credentials.bin legado: %s", exc)
                return username, password
        except Exception as e:
            if path == LEGACY_CREDENTIALS_FILE:
                try:
                    if path.read_bytes().lstrip().startswith(b"{"):
                        path.unlink(missing_ok=True)
                        logger.warning("Arquivo legado de credenciais em texto removido.")
                except OSError:
                    pass
            logger.warning("Nao foi possivel descriptografar %s: %s", path.name, e)

    return "Filhos", ""


def get_filhos_password() -> str:
    """Retorna apenas a senha atual da conta Filhos."""
    _, password = get_filhos_credentials()
    return password
