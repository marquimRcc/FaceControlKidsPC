"""Cliente mínimo para pam_exec; retorna zero somente para ticket facial fresco."""
from __future__ import annotations

import os
import socket
from pathlib import Path

from .session import linux_display_session


def main() -> int:
    pam_type = os.environ.get("PAM_TYPE", "")
    pam_user = os.environ.get("PAM_USER", "")
    expected_user = os.environ.get("FACEKIDS_CHILD_USER", "filhos")
    if pam_type != "auth" or pam_user.casefold() != expected_user.casefold():
        return 1
    session_id = linux_display_session(pam_user)
    if not session_id:
        return 1
    socket_path = Path(os.environ.get(
        "FACEKIDS_AUTH_SOCKET", "/run/facekids/auth.sock"
    ))
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(2.0)
    try:
        client.connect(str(socket_path))
        client.sendall(f"AUTH {session_id}\n".encode("ascii"))
        return 0 if client.recv(32).strip() == b"ALLOW" else 1
    except OSError:
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
