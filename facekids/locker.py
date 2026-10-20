"""Adaptador de bloqueio. A V1 começa SEM bloquear: --lock habilita."""
import os
import subprocess


def lock_current_session():
    if os.name=="nt":
        import ctypes
        result = ctypes.windll.user32.LockWorkStation()
        if result == 0:
            raise RuntimeError("Falha ao solicitar bloqueio ao Windows")
        return
    if os.name=="posix":
        # Requer systemd/logind e sessão ativa; a compatibilidade no Regata OS
        # ainda precisa ser testada na máquina real.
        subprocess.run(["loginctl","lock-session"],check=True,timeout=8)
        return
    raise NotImplementedError("Plataforma sem adaptador de bloqueio")
