"""Adaptador de bloqueio. A V1 começa SEM bloquear: --lock habilita."""
import os
import subprocess


def _validated_session_id(session_id: str | None) -> str | None:
    if session_id is None:
        return None
    if not session_id or not all(ch.isalnum() or ch in "_-" for ch in session_id):
        raise ValueError("Identificador de sessão inválido")
    return session_id


def lock_current_session(session_id: str | None = None):
    if os.name=="nt":
        import ctypes
        result = ctypes.windll.user32.LockWorkStation()
        if result == 0:
            raise RuntimeError("Falha ao solicitar bloqueio ao Windows")
        return
    if os.name=="posix":
        command = ["loginctl", "lock-session"]
        session_id = _validated_session_id(session_id)
        if session_id is not None:
            command.append(session_id)
        subprocess.run(command, check=True, timeout=8)
        return
    raise NotImplementedError("Plataforma sem adaptador de bloqueio")


def unlock_linux_session(session_id: str) -> None:
    """Solicita ao logind o desbloqueio de uma sessão Linux já autenticada."""
    if os.name != "posix":
        raise NotImplementedError("Desbloqueio por logind existe apenas no Linux")
    validated = _validated_session_id(session_id)
    subprocess.run(
        ["loginctl", "unlock-session", validated], check=True, timeout=8
    )
