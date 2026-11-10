"""Verifica o runtime e os recursos do EXE sem alterar a instalacao local."""
from pathlib import Path
import sys
import tkinter

from . import app_window, auth_service, boot_auth, filhos_agent
from .camera_service import MODELS_DIR, Recognizer


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    if Path(sys.base_prefix).resolve() != root / "runtime":
        return 2
    if not (root / "facekids/ui_assets/app.html").is_file():
        return 3
    if not (root / "native/credential_provider_facekids/FaceKidsCredentialProvider.dll").is_file():
        return 4
    if not (root / "scripts/Preparar-Perfil-Filhos.ps1").is_file():
        return 5
    tkinter.Tcl()
    Recognizer(MODELS_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
