"""Adaptador de bloqueio. A V1 começa SEM bloquear: --lock habilita."""
import os
import subprocess


def lock_current_session(session_id: str | None = None):
    if os.name=="nt":
        import ctypes
        result = ctypes.windll.user32.LockWorkStation()
        if result == 0:
            raise RuntimeError("Falha ao solicitar bloqueio ao Windows")
        return
    if os.name=="posix":
        command = ["loginctl", "lock-session"]
        if session_id:
            if not all(ch.isalnum() or ch in "_-" for ch in session_id):
                raise ValueError("Identificador de sessão inválido")
            command.append(session_id)
        subprocess.run(command, check=True, timeout=8)
        return
    raise NotImplementedError("Plataforma sem adaptador de bloqueio")
