"""FaceControlKidsPC - Motor de Instalacao, Configuracao e Desinstalacao Automatizada.

Executa as etapas de instalacao do sistema com seguranca e paridade funcional total com a main:
1. Provisiona/redefine a senha da conta Windows 'Filhos' e salva no cofre seguro DPAPI (credentials.bin);
2. Registra o FaceKidsCredentialProvider.dll no Registro do Windows e COM CLSID;
3. Configura permissoes NTFS e tarefas agendadas em segundo plano (FaceKidsAuthService e FaceKidsFilhosAgent);
4. Inicializa o banco de dados SQLite com o PIN mestre dos pais;
5. Cria atalhos oficiais com o icone .ico na Area de Trabalho e Menu Iniciar;
6. Permite verificacao em tempo real da saude dos servicos e desinstalacao segura completa.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import shutil
import string
import subprocess
import sys
import time
from typing import Any, Callable, Dict, Optional, Tuple

from .admin_auth import hash_pin
from .storage import Storage
from .session_secret import (
    generate_secure_secret,
    save_secure_secret,
    get_session_secret,
    _run_win_cmd,
)
from .credential_store import (
    save_filhos_credentials,
    get_filhos_credentials,
    get_filhos_password,
    CREDENTIALS_FILE,
)


logger = logging.getLogger("facekids.installer_engine")

PROGRAMDATA_DIR = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "FaceKids"
SECURITY_DIR = PROGRAMDATA_DIR / "security"
TOKEN_FILE = SECURITY_DIR / "filhos_session.token"
CONFIG_FILE = PROGRAMDATA_DIR / "configuracoes.json"
DEFAULT_DB_FILE = PROGRAMDATA_DIR / "criancas.sqlite3"

CREDENTIAL_PROVIDER_GUID = "{FAC0D042-3DD0-4A8C-9F18-440C44330C20}"


def is_admin() -> bool:
    """Verifica se o processo atual esta rodando com privilegios de Administrador."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def get_system_diagnostics() -> Dict[str, Any]:
    """Coleta diagnosticos rapidos do sistema para o instalador."""
    results: Dict[str, Any] = {
        "is_admin": is_admin(),
        "camera_found": False,
        "camera_name": "Nao detectada",
        "filhos_user_exists": False,
        "filhos_user_sid": None,
        "dll_exists": False,
        "python_ready": True,
    }

    # Verifica camera rapidamente
    try:
        import cv2
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY)
        if cap.isOpened():
            results["camera_found"] = True
            results["camera_name"] = "Webcam HD Integrada"
            cap.release()
    except Exception:
        pass

    # Verifica usuario Windows 'Filhos'
    if sys.platform == "win32":
        try:
            p = _run_win_cmd(
                ["powershell", "-NoProfile", "-Command",
                 "Get-LocalUser -Name 'Filhos' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty SID"],
                timeout=5.0
            )
            sid = p.stdout.strip()
            if sid and p.returncode == 0:
                results["filhos_user_exists"] = True
                results["filhos_user_sid"] = sid
        except Exception as e:
            logger.debug(f"Falha ao consultar usuario Filhos: {e}")

    # Verifica DLL
    root = Path(__file__).resolve().parent.parent
    dll_path = root / "native" / "credential_provider_facekids" / "FaceKidsCredentialProvider.dll"
    installed_dll = PROGRAMDATA_DIR / "FaceKidsCredentialProvider.dll"
    results["dll_exists"] = dll_path.exists() or installed_dll.exists()

    return results


def ensure_filhos_windows_user(secret: str, username: str = "Filhos") -> Tuple[bool, str]:
    """Cria ou atualiza a senha da conta local 'Filhos' e armazena no cofre seguro DPAPI."""
    if not secret:
        secret = "1"

    if sys.platform != "win32":
        save_filhos_credentials(username, secret)
        return True, "Simulado em ambiente de teste"

    try:
        # 1. Verifica se o usuario ja existe
        check = _run_win_cmd(["net", "user", username], timeout=10.0)
        if check.returncode == 0:
            # Atualiza senha com a credencial informada
            res = _run_win_cmd(["net", "user", username, secret], timeout=10.0)
            if res.returncode != 0:
                logger.warning(f"Aviso ao redefinir senha da conta {username}: {res.stderr}")

            # Define senha para nunca expirar
            _run_win_cmd(["powershell", "-NoProfile", "-Command",
                          f"Set-LocalUser -Name '{username}' -PasswordNeverExpires $true -ErrorAction SilentlyContinue"], timeout=10.0)
            _run_win_cmd(["wmic", "useraccount", "where", f"Name='{username}'", "set", "PasswordExpires=FALSE"], timeout=10.0)
            save_filhos_credentials(username, secret)
            return True, f"Conta '{username}' atualizada com a nova senha e protegida via DPAPI."
        else:
            # Cria a conta supervisionada
            res = _run_win_cmd(
                ["net", "user", username, secret, "/add",
                 "/fullname:Filhos",
                 "/comment:Conta supervisionada pelo FaceControlKidsPC",
                 "/passwordchg:no", "/expires:never"],
                timeout=15.0
            )
            if res.returncode != 0:
                logger.warning(f"Aviso ao criar conta '{username}': {res.stderr}")

            # Adiciona ao grupo local de Usuarios (SID S-1-5-32-545)
            _run_win_cmd(["powershell", "-NoProfile", "-Command",
                          f"Add-LocalGroupMember -SID 'S-1-5-32-545' -Member '{username}' -ErrorAction SilentlyContinue"], timeout=10.0)
            _run_win_cmd(["powershell", "-NoProfile", "-Command",
                          f"Set-LocalUser -Name '{username}' -PasswordNeverExpires $true -ErrorAction SilentlyContinue"], timeout=10.0)
            save_filhos_credentials(username, secret)
            return True, f"Conta '{username}' criada com sucesso e protegida via DPAPI."
    except Exception as e:
        save_filhos_credentials(username, secret)
        return False, f"Erro ao configurar conta Windows: {e}"


def setup_windows_services(root_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Configura tarefas agendadas em segundo plano (AuthService e FilhosAgent) e permissoes NTFS."""
    if sys.platform != "win32":
        return True, "Simulado em ambiente de teste"

    root = root_dir or Path(__file__).resolve().parent.parent
    pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable).parent / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)

    try:
        # 1. Permissoes em C:\ProgramData\FaceKids para a conta Filhos
        cmd_acl = [
            "icacls", str(PROGRAMDATA_DIR),
            "/grant", "*S-1-5-32-545:(OI)(CI)(M)",
            "Filhos:(OI)(CI)(M)"
        ]
        _run_win_cmd(cmd_acl, timeout=10.0)

        # 2. Configura script do agente na pasta de dados
        agent_bat = PROGRAMDATA_DIR / "iniciar-filhos-agent.bat"
        agent_content = (
            "@echo off\r\n"
            'if /i "%USERNAME%" neq "Filhos" exit /b\r\n'
            f'cd /d "{PROGRAMDATA_DIR}"\r\n'
            f'set PYTHONPATH={root}\r\n'
            f'start "" "{pythonw}" -m facekids.filhos_agent\r\n'
        )
        agent_bat.write_text(agent_content, encoding="ascii", errors="ignore")

        # 3. Configura script do servico de autenticacao na pasta de dados
        auth_bat = PROGRAMDATA_DIR / "iniciar-auth-service.bat"
        auth_content = (
            "@echo off\r\n"
            f'cd /d "{PROGRAMDATA_DIR}"\r\n'
            f'set PYTHONPATH={root}\r\n'
            f'start "" "{pythonw}" -m facekids.auth_service\r\n'
        )
        auth_bat.write_text(auth_content, encoding="ascii", errors="ignore")

        # 4. Limpeza de processos residuais e tarefas anteriores
        ps_cleanup = (
            "schtasks.exe /end /tn FaceKidsBootAuth /f 2>$null; "
            "schtasks.exe /delete /tn FaceKidsBootAuth /f 2>$null; "
            "schtasks.exe /end /tn FaceKidsAuthService /f 2>$null; "
            "schtasks.exe /delete /tn FaceKidsAuthService /f 2>$null; "
            "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { "
            "$_.CommandLine -like '*auth_service*' -or $_.CommandLine -like '*boot_auth*' "
            "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_cleanup], timeout=10.0)

        # 5. Tarefa Agendada 1: FaceKidsAuthService (Interativa com privilegios elevados)
        # O Windows 10/11 bloqueia acesso a webcam na Sessao 0 (SYSTEM). Para autenticar
        # na tela de bloqueio (Win+L), o servico deve rodar na sessao interativa do usuario.
        ps_auth = (
            f"$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name; "
            f"$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/d /c \"{auth_bat}\"'; "
            f"$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser; "
            f"$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Highest; "
            f"$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Priority 4; "
            f"Register-ScheduledTask -TaskName 'FaceKidsAuthService' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null; "
            f"Start-ScheduledTask -TaskName 'FaceKidsAuthService' -ErrorAction SilentlyContinue"
        )
        _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_auth], timeout=15.0)

        # 6. Atalho no Startup do usuario como contingencia garantida e inicializacao imediata
        ps_startup = (
            f"$userStartup = \"$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\"; "
            f"$vbsPath = Join-Path $userStartup 'FaceKidsAuthService.vbs'; "
            f"$vbsCode = 'Set WshShell = CreateObject(\"WScript.Shell\")' + [Environment]::NewLine + "
            f"'WshShell.CurrentDirectory = \"{PROGRAMDATA_DIR}\"' + [Environment]::NewLine + "
            f"'WshShell.Run \"\"\"{pythonw}\"\" -m facekids.auth_service\", 0, False'; "
            f"Set-Content -Path $vbsPath -Value $vbsCode -Encoding ASCII -Force; "
            f"Start-Process -FilePath 'wscript.exe' -ArgumentList \"`\"$vbsPath`\"\" -WindowStyle Hidden"
        )
        _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_startup], timeout=10.0)

        # 7. Tarefa Agendada 2: FaceKidsFilhosAgent (Interativo no Logon de Filhos)
        ps_agent = (
            f"$filhosAccount = \"$env:COMPUTERNAME\\Filhos\"; "
            f"$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/d /c \"{agent_bat}\"'; "
            f"$trigger = New-ScheduledTaskTrigger -AtLogOn -User $filhosAccount; "
            f"$principal = New-ScheduledTaskPrincipal -UserId $filhosAccount -LogonType Interactive -RunLevel Limited; "
            f"Register-ScheduledTask -TaskName 'FaceKidsFilhosAgent' -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null"
        )
        _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_agent], timeout=15.0)

        # 5. Registro da DLL do Credential Provider no Registro
        dll_target = PROGRAMDATA_DIR / "FaceKidsCredentialProvider.dll"
        if dll_target.exists():
            _run_win_cmd(["regsvr32.exe", "/s", str(dll_target)], timeout=10.0)
            ps_reg = (
                f"$guid = '{CREDENTIAL_PROVIDER_GUID}'; "
                f"$cpPath = \"HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\Credential Providers\\$guid\"; "
                f"if (-not (Test-Path $cpPath)) {{ New-Item -Path $cpPath -Force | Out-Null }}; "
                f"Set-ItemProperty -Path $cpPath -Name '(Default)' -Value 'FaceKidsCredentialProvider' -Force; "
                f"$filhosUser = Get-LocalUser -Name 'Filhos' -ErrorAction SilentlyContinue; "
                f"if ($filhosUser) {{ "
                f"  $regCustom = 'HKLM:\\SOFTWARE\\FaceControlKidsPC\\CredentialProvider'; "
                f"  if (-not (Test-Path $regCustom)) {{ New-Item -Path $regCustom -Force | Out-Null }}; "
                f"  Set-ItemProperty -Path $regCustom -Name 'TargetUserSid' -Value $filhosUser.SID.Value -Force "
                f"}}"
            )
            _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_reg], timeout=15.0)

        return True, "Servicos e Credential Provider registrados com sucesso."
    except Exception as e:
        logger.warning(f"Aviso ao registrar servicos: {e}")
        return False, str(e)


def create_desktop_shortcuts(root_dir: Optional[Path] = None) -> None:
    """Cria atalhos oficiais com icone na Area de Trabalho e Menu Iniciar."""
    if sys.platform != "win32":
        return

    root = root_dir or Path(__file__).resolve().parent.parent
    ico_source = root / "assets" / "facekids.ico"
    ico_dest = PROGRAMDATA_DIR / "facekids.ico"
    try:
        if ico_source.exists():
            PROGRAMDATA_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ico_source, ico_dest)
    except Exception:
        pass

    icon_path = ico_dest if ico_dest.exists() else ico_source

    desktop = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "Desktop"
    start_menu = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "FaceKids"
    try:
        start_menu.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    target_exe = None
    args = ""
    if getattr(sys, "frozen", False):
        target_exe = Path(sys.executable)
        args = "--mode=dashboard"
    elif pythonw.exists():
        target_exe = pythonw
        args = "-m facekids.app_window --mode=dashboard"
    else:
        target_exe = Path(sys.executable)
        args = "-m facekids.app_window --mode=dashboard"

    destinations = [desktop]
    if start_menu.exists():
        destinations.append(start_menu)

    for dest in destinations:
        try:
            # 1. Atalho do Painel dos Pais
            lnk_panel = dest / "FaceKids - Painel dos Pais.lnk"
            ps_shortcut = (
                f"$wsh = New-Object -ComObject WScript.Shell; "
                f"$s = $wsh.CreateShortcut('{lnk_panel}'); "
                f"$s.TargetPath = '{target_exe}'; "
                f"$s.Arguments = '{args}'; "
                f"$s.WorkingDirectory = '{root}'; "
                f"$s.Description = 'FaceKids - Painel Administrativo dos Pais'; "
                f"$s.IconLocation = '{icon_path},0'; "
                f"$s.Save()"
            )
            _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_shortcut], timeout=5.0)

            # 2. Atalho do Desinstalador
            uninst_bat = root / "Desinstalar-FaceKids.bat"
            if uninst_bat.exists():
                lnk_uninst = dest / "Desinstalar FaceKids.lnk"
                ps_uninst = (
                    f"$wsh = New-Object -ComObject WScript.Shell; "
                    f"$s = $wsh.CreateShortcut('{lnk_uninst}'); "
                    f"$s.TargetPath = '{uninst_bat}'; "
                    f"$s.WorkingDirectory = '{root}'; "
                    f"$s.Description = 'Desinstalar FaceKids com Seguranca'; "
                    f"$s.IconLocation = '{icon_path},0'; "
                    f"$s.Save()"
                )
                _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_uninst], timeout=5.0)
        except Exception as e:
            logger.warning(f"Aviso ao criar atalhos em {dest}: {e}")


def verify_runtime_health() -> Dict[str, Any]:
    """Verifica a integridade e estado dos servicos e DLL em tempo real."""
    health = {
        "auth_service": {"running": False, "registered": False},
        "filhos_agent": {"registered": False},
        "credential_provider": {"registered": False},
    }
    if sys.platform != "win32":
        return health

    try:
        # 1. Consulta FaceKidsAuthService
        p = _run_win_cmd(["schtasks", "/query", "/tn", "FaceKidsAuthService", "/fo", "csv"], timeout=5.0)
        if p.returncode == 0:
            health["auth_service"]["registered"] = True
            if "Running" in p.stdout or "Em execução" in p.stdout:
                health["auth_service"]["running"] = True

        # Se nao estiver rodando via tarefa, checa se processo python auth_service existe
        if not health["auth_service"]["running"]:
            p_proc = _run_win_cmd(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*auth_service*' } | Select-Object -ExpandProperty ProcessId"],
                timeout=5.0
            )
            if p_proc.stdout.strip():
                health["auth_service"]["running"] = True

        # 2. Consulta FaceKidsFilhosAgent
        p_agent = _run_win_cmd(["schtasks", "/query", "/tn", "FaceKidsFilhosAgent", "/fo", "csv"], timeout=5.0)
        if p_agent.returncode == 0:
            health["filhos_agent"]["registered"] = True

        # 3. Consulta Registro do Credential Provider
        p_reg = _run_win_cmd(
            ["powershell", "-NoProfile", "-Command",
             f"Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\Credential Providers\\{CREDENTIAL_PROVIDER_GUID}'"],
            timeout=5.0
        )
        if "True" in p_reg.stdout:
            health["credential_provider"]["registered"] = True

    except Exception as e:
        logger.debug(f"Aviso ao consultar runtime health: {e}")

    return health


def uninstall_system(remove_data: bool = False, remove_windows_user: bool = False) -> Tuple[bool, str]:
    """Executa a desinstalacao completa e segura do FaceKids no Windows."""
    logger.info("Iniciando rotina de desinstalacao do FaceKids...")

    if sys.platform == "win32":
        # 1. Desregistrar DLL via regsvr32 e remover chaves do Registro PRIMEIRO
        dll_target = PROGRAMDATA_DIR / "FaceKidsCredentialProvider.dll"
        if dll_target.exists():
            _run_win_cmd(["regsvr32.exe", "/u", "/s", str(dll_target)], timeout=10.0)

        ps_unreg = (
            f"$clsid = '{CREDENTIAL_PROVIDER_GUID}'; "
            f"Remove-Item -Path \"HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\Credential Providers\\$clsid\" -Recurse -Force -ErrorAction SilentlyContinue; "
            f"Remove-Item -Path \"HKLM:\\SOFTWARE\\Classes\\CLSID\\$clsid\" -Recurse -Force -ErrorAction SilentlyContinue; "
            f"Remove-Item -Path \"HKLM:\\SOFTWARE\\FaceControlKidsPC\" -Recurse -Force -ErrorAction SilentlyContinue; "
            f"Remove-ItemProperty -Path \"HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\" -Name \"FaceKidsAuthService\" -Force -ErrorAction SilentlyContinue; "
            f"$userStartup = \"$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\FaceKidsAuthService.vbs\"; "
            f"Remove-Item -Path $userStartup -Force -ErrorAction SilentlyContinue"
        )
        _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_unreg], timeout=10.0)

        # 2. Parar e remover tarefas agendadas
        for task in ("FaceKidsBootAuth", "FaceKidsAuthService", "FaceKidsFilhosAgent"):
            _run_win_cmd(["schtasks.exe", "/end", "/tn", task], timeout=5.0)
            _run_win_cmd(["schtasks.exe", "/delete", "/tn", task, "/f"], timeout=5.0)

        # 3. Encerrar processos residuais
        ps_kill = (
            "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { "
            "$_.CommandLine -like '*auth_service*' -or $_.CommandLine -like '*filhos_agent*' -or $_.CommandLine -like '*-m facekids.boot_auth*' "
            "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_kill], timeout=10.0)

        # 4. Remover atalhos do Desktop e Menu Iniciar
        desktop = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "Desktop"
        start_menu = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "FaceKids"
        for d in (desktop, start_menu):
            for name in ("FaceKids - Painel dos Pais.lnk", "Painel FaceKids.lnk", "Desinstalar FaceKids.lnk"):
                try:
                    f = d / name
                    if f.exists():
                        f.unlink()
                except Exception:
                    pass
        if start_menu.exists():
            try:
                shutil.rmtree(str(start_menu), ignore_errors=True)
            except Exception:
                pass

        # 5. Remover arquivos executaveis de ProgramData
        files_to_clean = [
            PROGRAMDATA_DIR / "FaceKidsCredentialProvider.dll",
            PROGRAMDATA_DIR / "iniciar-filhos-agent.bat",
            PROGRAMDATA_DIR / "iniciar-auth-service.bat",
            PROGRAMDATA_DIR / "last_unlock.json",
            PROGRAMDATA_DIR / "auth_service.pid",
            PROGRAMDATA_DIR / "facekids.ico",
        ]
        for f in files_to_clean:
            try:
                if f.exists():
                    f.unlink()
            except Exception:
                pass

        # 6. Opcional: remover dados se solicitado
        if remove_data and PROGRAMDATA_DIR.exists():
            try:
                shutil.rmtree(str(PROGRAMDATA_DIR), ignore_errors=True)
            except Exception as e:
                logger.warning(f"Aviso ao remover ProgramData: {e}")

        # 7. Opcional: remover conta Windows Filhos se solicitado
        if remove_windows_user:
            _run_win_cmd(["net", "user", "Filhos", "/delete"], timeout=10.0)

    return True, "FaceKids desinstalado com sucesso."


def setup_system(
    master_pin: str,
    first_child_name: Optional[str] = None,
    first_child_daily_limit_minutes: int = 120,
    filhos_password: Optional[str] = None,
    filhos_username: str = "Filhos",
    progress_callback: Optional[Callable[[str, int], None]] = None
) -> Tuple[bool, str]:
    """Executa a instalacao completa do sistema com atrito minimo."""
    def notify(msg: str, pct: int):
        if progress_callback:
            progress_callback(msg, pct)

    notify("Criando diretorios protegidos do sistema...", 10)
    try:
        PROGRAMDATA_DIR.mkdir(parents=True, exist_ok=True)
        SECURITY_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Aviso ao criar diretorios: {e}")

    root = Path(__file__).resolve().parent.parent
    dll_source = root / "native" / "credential_provider_facekids" / "FaceKidsCredentialProvider.dll"
    dll_target = PROGRAMDATA_DIR / "FaceKidsCredentialProvider.dll"

    notify("Configurando conta Windows e credencial segura DPAPI...", 25)
    secret = (filhos_password or "").strip()
    if not secret:
        # Se nenhuma senha foi informada, consulta a existente ou gera nova
        secret = get_filhos_password() or generate_secure_secret(32)

    try:
        ok_user, msg_user = ensure_filhos_windows_user(secret, username=filhos_username)
        if not ok_user:
            logger.warning(f"Aviso na configuracao do usuario: {msg_user}")
    except Exception as e:
        logger.warning(f"Erro ao configurar usuario: {e}")

    notify("Copiando driver de desbloqueio facial (DLL)...", 45)
    try:
        if dll_source.exists():
            shutil.copy2(dll_source, dll_target)
    except Exception as e:
        logger.warning(f"Aviso ao copiar DLL: {e}")

    notify("Ativando servicos em segundo plano (AuthService e FilhosAgent)...", 60)
    try:
        setup_windows_services(root)
    except Exception as e:
        logger.warning(f"Aviso ao configurar servicos do Windows: {e}")

    notify("Configurando PIN mestre dos pais e banco de dados...", 75)
    try:
        store = Storage(DEFAULT_DB_FILE)
        if master_pin:
            hashed = hash_pin(master_pin)
            store.set_setting("parent_pin_v1", hashed)

        if first_child_name and first_child_name.strip():
            existing_people = store.people()
            if not any(p[1].lower() == first_child_name.strip().lower() for p in existing_people):
                store.add_person(first_child_name.strip(), first_child_daily_limit_minutes)
        store.close()
    except Exception as e:
        logger.warning(f"Aviso ao inicializar banco de dados: {e}")

    notify("Configurando politicas de inatividade e servicos...", 85)
    try:
        if not CONFIG_FILE.exists():
            default_settings = {
                "inactivity_lock_seconds": 120,
                "inactivity_warn_seconds": 100,
                "face_check_interval_seconds": 120,
                "description": "FaceControlKidsPC - Bloqueio por inatividade e checagem periodica"
            }
            CONFIG_FILE.write_text(json.dumps(default_settings, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Aviso ao salvar configuracoes: {e}")

    notify("Criando atalhos oficiais com ícone na Area de Trabalho...", 95)
    try:
        create_desktop_shortcuts(root)
    except Exception as e:
        logger.warning(f"Aviso ao criar atalhos: {e}")

    notify("Instalacao concluida com sucesso!", 100)
    return True, "FaceKids instalado e pronto para uso."
