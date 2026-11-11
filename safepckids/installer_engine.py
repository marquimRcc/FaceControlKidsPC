"""SafePCKids - Motor de Instalacao, Configuracao e Desinstalacao Automatizada.

Executa as etapas de instalacao do sistema com seguranca e paridade funcional total com a main:
1. Provisiona/redefine a senha da conta Windows 'Filhos' e salva no cofre seguro DPAPI (credentials.bin);
2. Registra o SafePCKidsCredentialProvider.dll no Registro do Windows e COM CLSID;
3. Configura permissoes NTFS e tarefas agendadas em segundo plano (SafePCKidsAuthService e SafePCKidsFilhosAgent);
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
    save_secure_secret,
    get_session_secret,
    _run_win_cmd,
)
from .credential_store import (
    save_filhos_credentials,
    get_filhos_credentials,
    CREDENTIALS_FILE,
)


logger = logging.getLogger("safepckids.installer_engine")

PROGRAMDATA_DIR = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "SafePCKids"
SECURITY_DIR = PROGRAMDATA_DIR / "security"
TOKEN_FILE = SECURITY_DIR / "filhos_session.token"
CONFIG_FILE = PROGRAMDATA_DIR / "configuracoes.json"
DEFAULT_DB_FILE = PROGRAMDATA_DIR / "criancas.sqlite3"
INSTALL_MARKER = PROGRAMDATA_DIR / "installation-ready.json"

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
    root = get_production_project_root()
    dll_path = root / "native" / "credential_provider_safepckids" / "SafePCKidsCredentialProvider.dll"
    installed_dll = PROGRAMDATA_DIR / "SafePCKidsCredentialProvider.dll"
    results["dll_exists"] = dll_path.exists() or installed_dll.exists()

    return results


def ensure_filhos_windows_user(secret: str, username: str = "Filhos", *,
                              preserve_existing: bool = False) -> Tuple[bool, str]:
    """Cria ou atualiza a senha da conta local 'Filhos' e armazena no cofre seguro DPAPI."""
    if username != "Filhos":
        return False, "O nome da conta supervisionada deve ser Filhos."
    if not secret and not preserve_existing:
        return False, "Informe a senha da conta Filhos."

    if sys.platform != "win32":
        save_filhos_credentials(username, secret)
        return True, "Simulado em ambiente de teste"

    try:
        # NetUserGetInfo distingue conta ausente de falhas de consulta.
        buffer = ctypes.c_void_p()
        status = ctypes.windll.netapi32.NetUserGetInfo(
            None, ctypes.c_wchar_p(username), 0, ctypes.byref(buffer)
        )
        if buffer:
            ctypes.windll.netapi32.NetApiBufferFree(buffer)
        if status not in (0, 2221):
            return False, f"Nao foi possivel consultar a conta Filhos (Windows {status})."
        if status == 0:
            if preserve_existing:
                stored_user, stored_password = get_filhos_credentials(default_password="")
                if stored_user == username and stored_password:
                    return True, "Conta Filhos existente preservada."
                if not secret:
                    return False, "Informe a senha atual da conta Filhos para vincula-la ao SafePCKids."
                token = wintypes.HANDLE()
                if not ctypes.windll.advapi32.LogonUserW(
                    ctypes.c_wchar_p(username), ctypes.c_wchar_p("."), ctypes.c_wchar_p(secret),
                    2, 0, ctypes.byref(token),
                ):
                    return False, "O Windows nao aceitou a senha atual de Filhos. A conta foi preservada."
                ctypes.windll.kernel32.CloseHandle(token)
                if not save_filhos_credentials(username, secret):
                    return False, "Nao foi possivel guardar a credencial no SafePCKids."
                return True, "Conta Filhos existente vinculada e preservada."
            # Atualiza senha com a credencial informada
            res = _run_win_cmd(["net", "user", username, secret], timeout=5.0)
            if res.returncode != 0:
                return False, f"Nao foi possivel atualizar a senha da conta Filhos: {res.stderr.strip()}"

            # Define senha para nunca expirar
            _run_win_cmd(
                ["powershell", "-NoProfile", "-Command",
                 f"Set-LocalUser -Name '{username}' -PasswordNeverExpires $true -ErrorAction SilentlyContinue"],
                timeout=5.0,
                capture=False,
            )
            if not save_filhos_credentials(username, secret):
                return False, "A senha foi alterada no Windows, mas nao foi salva no cofre de credenciais."
            return True, f"Conta '{username}' atualizada com a nova senha e protegida via DPAPI."
        else:
            secret = secret or "1"
            # Cria a conta supervisionada
            res = _run_win_cmd(
                ["net", "user", username, secret, "/add",
                 "/fullname:Filhos",
                 "/comment:Conta supervisionada pelo SafePCKids",
                 "/passwordchg:no", "/expires:never"],
                timeout=5.0
            )
            if res.returncode != 0:
                return False, "O Windows nao criou a conta Filhos. Verifique a politica de senha e tente novamente."

            # Adiciona ao grupo local de Usuarios (SID S-1-5-32-545)
            _run_win_cmd(
                ["powershell", "-NoProfile", "-Command",
                 f"Add-LocalGroupMember -SID 'S-1-5-32-545' -Member '{username}' -ErrorAction SilentlyContinue"],
                timeout=5.0,
                capture=False,
            )
            _run_win_cmd(
                ["powershell", "-NoProfile", "-Command",
                 f"Set-LocalUser -Name '{username}' -PasswordNeverExpires $true -ErrorAction SilentlyContinue"],
                timeout=5.0,
                capture=False,
            )
            if preserve_existing:
                profile_script = get_production_project_root() / "scripts" / "Preparar-Perfil-Filhos.ps1"
                _require_win_cmd(
                    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                     "-File", str(profile_script)],
                    "Preparacao do primeiro acesso de Filhos", timeout=60.0,
                )
            if not save_filhos_credentials(username, secret):
                return False, "A conta Filhos foi criada, mas a senha nao foi salva no cofre de credenciais."
            return True, f"Conta '{username}' criada com sucesso e protegida via DPAPI."
    except Exception as e:
        return False, f"Erro ao configurar conta Windows: {e}"


def get_production_project_root() -> Path:
    """Retorna o diretorio raiz do projeto SafePCKids no disco."""
    env_root = os.environ.get("SAFEPCKIDS_ROOT")
    if env_root and Path(env_root).exists():
        return Path(env_root).resolve()

    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        parent_repo = exe_path.parent.parent
        if (parent_repo / ".venv" / "Scripts" / "pythonw.exe").exists() or (parent_repo / "safepckids").exists():
            return parent_repo
        if (exe_path.parent / ".venv" / "Scripts" / "pythonw.exe").exists() or (exe_path.parent / "safepckids").exists():
            return exe_path.parent

    here = Path(__file__).resolve().parent.parent
    if (here / ".venv" / "Scripts" / "pythonw.exe").exists() or (here / "safepckids").exists():
        return here

    default_git = Path(r"C:\Users\MarcosMiniPC\Documents\git\SafePCKids")
    if default_git.exists():
        return default_git

    return here


def get_production_pythonw(root: Path) -> Path:
    """Localiza o interpretador pythonw para execucao limpa e sem UAC."""
    private_pythonw = root / "runtime" / "pythonw.exe"
    if private_pythonw.is_file():
        return private_pythonw
    venv_pythonw = root / ".venv" / "Scripts" / "pythonw.exe"
    if venv_pythonw.exists():
        return venv_pythonw.resolve()

    pyw_which = shutil.which("pythonw.exe")
    if pyw_which and Path(pyw_which).exists():
        return Path(pyw_which).resolve()

    pyw_sys = Path(sys.executable).parent / "pythonw.exe"
    if pyw_sys.exists():
        return pyw_sys.resolve()

    return Path(sys.executable).resolve()


def provider_dll(root: Path) -> Path:
    if (root / "runtime" / "pythonw.exe").is_file():
        return root / "native" / "credential_provider_safepckids" / "SafePCKidsCredentialProvider.dll"
    return PROGRAMDATA_DIR / "SafePCKidsCredentialProvider.dll"


def _require_win_cmd(command: list[str], step: str, timeout: float = 15.0) -> None:
    """Executa uma etapa obrigatoria e preserva a falha para a interface."""
    result = _run_win_cmd(command, timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "erro sem detalhes").strip()
        raise RuntimeError(f"{step}: {detail}")


def setup_windows_services(root_dir: Optional[Path] = None) -> Tuple[bool, str]:
    """Configura tarefas agendadas em segundo plano (AuthService e FilhosAgent) e permissoes NTFS com paridade total com a main."""
    if sys.platform != "win32":
        return True, "Simulado em ambiente de teste"

    root = root_dir or get_production_project_root()
    pythonw = get_production_pythonw(root)

    if not pythonw.exists():
        return False, f"Python do SafePCKids nao encontrado: {pythonw}"

    try:
        # 1. Permissoes NTFS para a conta Filhos (paridade exata com a branch main)
        cmd_acl_prog = [
            "icacls", str(PROGRAMDATA_DIR),
            "/grant", "*S-1-5-32-545:(OI)(CI)(M)",
            "Filhos:(OI)(CI)(M)"
        ]
        _require_win_cmd(cmd_acl_prog, "Permissoes dos dados do SafePCKids")

        cmd_acl_root = [
            "icacls", str(root),
            "/grant", "Filhos:(OI)(CI)(RX)"
        ]
        _require_win_cmd(cmd_acl_root, "Permissoes de leitura para a conta Filhos")

        user_profile = os.environ.get("USERPROFILE")
        if user_profile and not (root / "runtime" / "pythonw.exe").is_file():
            _run_win_cmd(["icacls", user_profile, "/grant", "Filhos:(RX)"], timeout=5.0, capture=False)

        local_python = os.environ.get("LOCALAPPDATA")
        if local_python and not (root / "runtime" / "pythonw.exe").is_file():
            py_dir = Path(local_python) / "Programs" / "Python"
            if py_dir.exists():
                _run_win_cmd(["icacls", str(py_dir), "/grant", "Filhos:(OI)(CI)(RX)", "/T"], timeout=5.0, capture=False)

        # 2. Runtime Tcl/Tk para a tela grafica de boas-vindas do agente na sessao de Filhos
        tcl_dir = PROGRAMDATA_DIR / "tcl"
        tcl_86 = tcl_dir / "tcl8.6"
        tk_86 = tcl_dir / "tk8.6"
        if not (tcl_86.exists() and tk_86.exists()):
            try:
                base_py = Path(sys.base_prefix) if hasattr(sys, "base_prefix") else pythonw.parent.parent
                tcl_src = base_py / "tcl"
                if tcl_src.exists():
                    tcl_dir.mkdir(parents=True, exist_ok=True)
                    if (tcl_src / "tcl8.6").exists() and not tcl_86.exists():
                        shutil.copytree(str(tcl_src / "tcl8.6"), str(tcl_86), dirs_exist_ok=True)
                    if (tcl_src / "tk8.6").exists() and not tk_86.exists():
                        shutil.copytree(str(tcl_src / "tk8.6"), str(tk_86), dirs_exist_ok=True)
            except Exception as e:
                logger.warning(f"Aviso ao copiar runtime Tcl/Tk: {e}")

        tcl_env_lines = ""
        if tcl_86.exists() and tk_86.exists():
            tcl_env_lines = (
                f'set TCL_LIBRARY={tcl_86}\r\n'
                f'set TK_LIBRARY={tk_86}\r\n'
            )

        # 3. Configura script do agente na pasta de dados (executa SEMPRE com pythonw, sem UAC)
        agent_bat = PROGRAMDATA_DIR / "iniciar-filhos-agent.bat"
        agent_content = (
            "@echo off\r\n"
            'echo [%date% %time%] Startup solicitado para %USERNAME% >> "C:\\ProgramData\\SafePCKids\\filhos_startup.log"\r\n'
            'if /i "%USERNAME%" neq "Filhos" exit /b\r\n'
            f'cd /d "{PROGRAMDATA_DIR}"\r\n'
            f'set PYTHONPATH={root}\r\n'
            f'{tcl_env_lines}'
            f'start "" "{pythonw}" -m safepckids.filhos_agent\r\n'
        )
        if not (root / "runtime" / "pythonw.exe").is_file():
            agent_bat.write_text(agent_content, encoding="ascii", errors="ignore")

        # 4. Configura script do servico de autenticacao na pasta de dados
        auth_bat = PROGRAMDATA_DIR / "iniciar-auth-service.bat"
        auth_content = (
            "@echo off\r\n"
            f'cd /d "{root}"\r\n'
            f'set PYTHONPATH={root}\r\n'
            f'start "" "{pythonw}" -m safepckids.auth_service\r\n'
        )
        if not (root / "runtime" / "pythonw.exe").is_file():
            auth_bat.write_text(auth_content, encoding="ascii", errors="ignore")

        # 5. Limpeza de processos residuais e tarefas anteriores (com protecao ao PID atual)
        current_pid = os.getpid()
        ps_cleanup = (
            "schtasks.exe /end /tn SafePCKidsBootAuth 2>$null; "
            "schtasks.exe /delete /tn SafePCKidsBootAuth /f 2>$null; "
            "schtasks.exe /end /tn SafePCKidsAuthService 2>$null; "
            "schtasks.exe /delete /tn SafePCKidsAuthService /f 2>$null; "
            f"Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {{ "
            f"$_.ProcessId -ne $PID -and $_.ProcessId -ne {current_pid} -and "
            f"($_.Name -like 'python*') -and "
            f"($_.CommandLine -like '*safepckids.auth_service*' -or $_.CommandLine -like '*safepckids.boot_auth*') "
            f"}} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"
        )
        _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_cleanup], timeout=30.0, capture=False)

        # 6. Tarefa Agendada 1: SafePCKidsAuthService (Interativa no logon do ADMINISTRADOR com privilegios elevados)
        # O servico de autenticacao de webcam roda na sessao do administrador para atender o Win+L
        ps_auth = (
            f"$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name; "
            f"$action = New-ScheduledTaskAction -Execute '{pythonw}' -Argument '-m safepckids.auth_service' -WorkingDirectory '{root}'; "
            f"$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser; "
            f"$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Highest; "
            f"$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Priority 4; "
            f"Register-ScheduledTask -TaskName 'SafePCKidsAuthService' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null; "
            f"Start-ScheduledTask -TaskName 'SafePCKidsAuthService' -ErrorAction SilentlyContinue"
        )
        _require_win_cmd(["powershell", "-NoProfile", "-Command", "$ErrorActionPreference = 'Stop'; " + ps_auth], "Tarefa SafePCKidsAuthService")

        # O pacote autonomo usa somente as tarefas agendadas.
        private_runtime = (root / "runtime" / "pythonw.exe").is_file()
        if private_runtime:
            startup = Path(os.environ["PROGRAMDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
            for name in ("SafePCKidsFilhosAgent.vbs", "SafePCKidsAuthService.vbs"):
                (startup / name).unlink(missing_ok=True)
            startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
            (startup / "SafePCKidsAuthService.vbs").unlink(missing_ok=True)
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", 0,
                                winreg.KEY_SET_VALUE) as run:
                try:
                    winreg.DeleteValue(run, "SafePCKidsAuthService")
                except FileNotFoundError:
                    pass

        # 7. Inicializacao de contingencia do modo de desenvolvimento
        # A. Startup Global: APENAS SafePCKidsFilhosAgent.vbs (ele filtra se %USERNAME% == "Filhos")
        try:
            global_startup = Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup")
            if not private_runtime and global_startup.exists():
                # Remove qualquer SafePCKidsAuthService legado do Startup global para nao tentar rodar em outras contas
                legacy_auth = global_startup / "SafePCKidsAuthService.vbs"
                if legacy_auth.exists():
                    try:
                        legacy_auth.unlink()
                    except Exception:
                        pass

                agent_vbs = global_startup / "SafePCKidsFilhosAgent.vbs"
                agent_vbs_code = (
                    'Option Explicit\r\n'
                    'Dim shell\r\n'
                    'Set shell = CreateObject("WScript.Shell")\r\n'
                    f'shell.Run "cmd.exe /d /c \"\"{agent_bat}\"\"", 0, False\r\n'
                )
                agent_vbs.write_text(agent_vbs_code, encoding="ascii", errors="replace")
        except Exception as e:
            logger.warning(f"Aviso ao registrar SafePCKidsFilhosAgent no Startup global: {e}")

        # B. Startup do Usuario Administrador: contingencia do SafePCKidsAuthService.vbs
        try:
            appdata_dir = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
            vbs_startup = Path(appdata_dir) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "SafePCKidsAuthService.vbs"
            if not private_runtime and vbs_startup.parent.exists():
                vbs_code = (
                    'Set WshShell = CreateObject("WScript.Shell")\r\n'
                    f'WshShell.CurrentDirectory = "{root}"\r\n'
                    f'WshShell.Run """{pythonw}"" -m safepckids.auth_service", 0, False\r\n'
                )
                vbs_startup.write_text(vbs_code, encoding="ascii", errors="replace")
        except Exception as e:
            logger.warning(f"Aviso ao registrar VBS no Startup: {e}")

        # 8. Tarefa Agendada 2: SafePCKidsFilhosAgent (Interativo no Logon de Filhos - PRIVILEGIOS LIMITADOS, SEM UAC)
        ps_agent = (
            f"$filhosAccount = \"$env:COMPUTERNAME\\Filhos\"; "
            f"$action = New-ScheduledTaskAction -Execute '{pythonw}' -Argument '-m safepckids.filhos_agent' -WorkingDirectory '{root}'; "
            f"$trigger = New-ScheduledTaskTrigger -AtLogOn -User $filhosAccount; "
            f"$principal = New-ScheduledTaskPrincipal -UserId $filhosAccount -LogonType Interactive -RunLevel Limited; "
            f"$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Priority 4; "
            f"Register-ScheduledTask -TaskName 'SafePCKidsFilhosAgent' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null"
        )
        _require_win_cmd(["powershell", "-NoProfile", "-Command", "$ErrorActionPreference = 'Stop'; " + ps_agent], "Tarefa SafePCKidsFilhosAgent")

        # 9. Registro da DLL do Credential Provider no Registro
        dll_target = provider_dll(root)
        if not dll_target.exists():
            raise RuntimeError(f"DLL do Credential Provider nao encontrada: {dll_target}")
        if dll_target.exists():
            _require_win_cmd(["regsvr32.exe", "/s", str(dll_target)], "Registro da DLL do Credential Provider")
            ps_reg = (
                f"$guid = '{CREDENTIAL_PROVIDER_GUID}'; "
                f"$cpPath = \"HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\Credential Providers\\$guid\"; "
                f"if (-not (Test-Path $cpPath)) {{ New-Item -Path $cpPath -Force | Out-Null }}; "
                f"Set-ItemProperty -Path $cpPath -Name '(Default)' -Value 'SafePCKidsCredentialProvider' -Force; "
                f"$filhosUser = Get-LocalUser -Name 'Filhos' -ErrorAction SilentlyContinue; "
                f"if ($filhosUser) {{ "
                f"  $regCustom = 'HKLM:\\SOFTWARE\\SafePCKids\\CredentialProvider'; "
                f"  if (-not (Test-Path $regCustom)) {{ New-Item -Path $regCustom -Force | Out-Null }}; "
                f"  Set-ItemProperty -Path $regCustom -Name 'TargetUserSid' -Value $filhosUser.SID.Value -Force "
                f"}}"
            )
            _require_win_cmd(["powershell", "-NoProfile", "-Command", "$ErrorActionPreference = 'Stop'; " + ps_reg], "Registro da conta Filhos no Credential Provider")

        # 10. O boot depende da DLL ja registrada e do banco inicializado.
        boot_script = root / "scripts" / "Ativar-Desbloqueio-No-Boot.ps1"
        if not boot_script.exists():
            raise RuntimeError(f"Script de autenticacao no boot ausente: {boot_script}")
        _require_win_cmd(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(boot_script)],
            "Autenticacao facial no boot", timeout=60.0,
        )

        for task in ("SafePCKidsAuthService", "SafePCKidsFilhosAgent", "SafePCKidsBootAuth"):
            _require_win_cmd(["schtasks", "/query", "/tn", task], f"Verificacao da tarefa {task}")

        return True, "Servicos e Credential Provider registrados com sucesso."
    except Exception as e:
        logger.warning(f"Aviso ao registrar servicos: {e}")
        return False, str(e)


def create_desktop_shortcuts(root_dir: Optional[Path] = None) -> None:
    """Cria atalhos oficiais com icone na Area de Trabalho e Menu Iniciar."""
    if sys.platform != "win32":
        return

    root = root_dir or get_production_project_root()
    ico_source = root / "assets" / "safepckids.ico"
    ico_dest = PROGRAMDATA_DIR / "safepckids.ico"
    try:
        if ico_source.exists():
            PROGRAMDATA_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ico_source, ico_dest)
    except Exception:
        pass

    icon_path = ico_dest if ico_dest.exists() else ico_source

    desktop = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "Desktop"
    start_menu = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "SafePCKids"
    try:
        start_menu.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    pythonw = get_production_pythonw(root)
    target_exe = None
    args = ""
    # Prioriza sempre o pythonw.exe assinado para evitar bloqueio do Smart App Control do Windows 11
    if pythonw.exists():
        target_exe = pythonw
        args = "-m safepckids.launcher --admin"
    elif getattr(sys, "frozen", False):
        target_exe = Path(sys.executable)
        args = "--admin"
    else:
        target_exe = Path(sys.executable)
        args = "-m safepckids.launcher --admin"

    destinations = [desktop]
    if start_menu.exists():
        destinations.append(start_menu)

    panel_links = 0
    for dest in destinations:
        try:
            # 1. Atalho do Painel dos Pais
            lnk_panel = dest / "SafePCKids - Painel dos Pais.lnk"
            ps_shortcut = (
                f"$wsh = New-Object -ComObject WScript.Shell; "
                f"$s = $wsh.CreateShortcut('{lnk_panel}'); "
                f"$s.TargetPath = '{target_exe}'; "
                f"$s.Arguments = '{args}'; "
                f"$s.WorkingDirectory = '{root}'; "
                f"$s.Description = 'SafePCKids - Painel Administrativo dos Pais'; "
                f"$s.IconLocation = '{icon_path},0'; "
                f"$s.Save()"
            )
            _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_shortcut], timeout=5.0, capture=False)
            if lnk_panel.is_file():
                panel_links += 1

            # 2. Atalho do Desinstalador
            uninst_bat = root / "scripts" / "Desinstalar-SafePCKids.bat"
            if not uninst_bat.exists():
                uninst_bat = root / "Desinstalar-SafePCKids.bat"
            if uninst_bat.exists():
                lnk_uninst = dest / "Desinstalar SafePCKids.lnk"
                ps_uninst = (
                    f"$wsh = New-Object -ComObject WScript.Shell; "
                    f"$s = $wsh.CreateShortcut('{lnk_uninst}'); "
                    f"$s.TargetPath = '{uninst_bat}'; "
                    f"$s.WorkingDirectory = '{root}'; "
                    f"$s.Description = 'Desinstalar SafePCKids com Seguranca'; "
                    f"$s.IconLocation = '{icon_path},0'; "
                    f"$s.Save()"
                )
                _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_uninst], timeout=5.0, capture=False)
        except Exception as e:
            logger.warning(f"Aviso ao criar atalhos em {dest}: {e}")

    if panel_links != 2:
        raise RuntimeError("Nao foi possivel criar o Painel dos Pais na Area de Trabalho e no Menu Iniciar.")


def verify_runtime_health() -> Dict[str, Any]:
    """Verifica a integridade e estado dos servicos e DLL em tempo real."""
    health = {
        "auth_service": {"running": False, "registered": False},
        "filhos_agent": {"registered": False},
        "boot_auth": {"registered": False},
        "credential_provider": {"registered": False},
        "filhos_user": {"exists": False},
    }
    if sys.platform != "win32":
        return health

    try:
        # 1. Consulta SafePCKidsAuthService
        p = _run_win_cmd(["schtasks", "/query", "/tn", "SafePCKidsAuthService", "/fo", "csv"], timeout=5.0)
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

        # 2. Consulta SafePCKidsFilhosAgent
        p_agent = _run_win_cmd(["schtasks", "/query", "/tn", "SafePCKidsFilhosAgent", "/fo", "csv"], timeout=5.0)
        if p_agent.returncode == 0:
            health["filhos_agent"]["registered"] = True

        p_boot = _run_win_cmd(["schtasks", "/query", "/tn", "SafePCKidsBootAuth"], timeout=5.0)
        health["boot_auth"]["registered"] = p_boot.returncode == 0
        p_user = _run_win_cmd(["net", "user", "Filhos"], timeout=5.0)
        health["filhos_user"]["exists"] = p_user.returncode == 0

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
    """Executa a desinstalacao completa e segura do SafePCKids no Windows."""
    logger.info("Iniciando rotina de desinstalacao do SafePCKids...")

    if sys.platform == "win32":
        # 1. Desregistrar DLL via regsvr32 e remover chaves do Registro PRIMEIRO
        dll_target = PROGRAMDATA_DIR / "SafePCKidsCredentialProvider.dll"
        if dll_target.exists():
            _run_win_cmd(["regsvr32.exe", "/u", "/s", str(dll_target)], timeout=10.0)

        ps_unreg = (
            f"$clsid = '{CREDENTIAL_PROVIDER_GUID}'; "
            f"Remove-Item -Path \"HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Authentication\\Credential Providers\\$clsid\" -Recurse -Force -ErrorAction SilentlyContinue; "
            f"Remove-Item -Path \"HKLM:\\SOFTWARE\\Classes\\CLSID\\$clsid\" -Recurse -Force -ErrorAction SilentlyContinue; "
            f"Remove-Item -Path \"HKLM:\\SOFTWARE\\SafePCKids\" -Recurse -Force -ErrorAction SilentlyContinue; "
            f"Remove-ItemProperty -Path \"HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run\" -Name \"SafePCKidsAuthService\" -Force -ErrorAction SilentlyContinue; "
            f"$userStartup = \"$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\SafePCKidsAuthService.vbs\"; "
            f"$globalStartup = 'C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\SafePCKidsFilhosAgent.vbs'; "
            f"Remove-Item -Path $globalStartup -Force -ErrorAction SilentlyContinue; "
            f"$globalAuth = 'C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Startup\\SafePCKidsAuthService.vbs'; "
            f"Remove-Item -Path $globalAuth -Force -ErrorAction SilentlyContinue; "
            f"Remove-Item -Path $userStartup -Force -ErrorAction SilentlyContinue"
        )
        _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_unreg], timeout=10.0)

        # 2. Parar e remover tarefas agendadas
        for task in ("SafePCKidsBootAuth", "SafePCKidsAuthService", "SafePCKidsFilhosAgent"):
            _run_win_cmd(["schtasks.exe", "/end", "/tn", task], timeout=5.0, capture=False)
            _run_win_cmd(["schtasks.exe", "/delete", "/tn", task, "/f"], timeout=5.0, capture=False)

        # 3. Encerrar processos residuais
        ps_kill = (
            "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { "
            "$_.CommandLine -like '*auth_service*' -or $_.CommandLine -like '*filhos_agent*' -or $_.CommandLine -like '*-m safepckids.boot_auth*' "
            "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        _run_win_cmd(["powershell", "-NoProfile", "-Command", ps_kill], timeout=10.0)

        # 4. Remover atalhos do Desktop e Menu Iniciar
        desktop = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "Desktop"
        start_menu = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "SafePCKids"
        for d in (desktop, start_menu):
            for name in ("SafePCKids - Painel dos Pais.lnk", "Painel SafePCKids.lnk", "Desinstalar SafePCKids.lnk"):
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
            PROGRAMDATA_DIR / "SafePCKidsCredentialProvider.dll",
            PROGRAMDATA_DIR / "iniciar-filhos-agent.bat",
            PROGRAMDATA_DIR / "iniciar-auth-service.bat",
            PROGRAMDATA_DIR / "last_unlock.json",
            PROGRAMDATA_DIR / "auth_service.pid",
            PROGRAMDATA_DIR / "safepckids.ico",
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

    return True, "SafePCKids desinstalado com sucesso."


def setup_system(
    master_pin: str,
    first_child_name: Optional[str] = None,
    first_child_daily_limit_minutes: int = 120,
    filhos_password: Optional[str] = None,
    filhos_username: str = "Filhos",
    progress_callback: Optional[Callable[[str, int], None]] = None,
    defer_services: bool = False,
) -> Tuple[bool, str]:
    """Instala e confirma todas as integracoes antes de declarar sucesso."""
    def notify(msg: str, pct: int):
        if progress_callback:
            progress_callback(msg, pct)

    if filhos_username != "Filhos":
        return False, "A conta supervisionada deve se chamar Filhos."
    if sys.platform == "win32" and not is_admin():
        return False, "Abra o instalador com permissao de administrador."

    root = get_production_project_root()
    if sys.platform == "win32":
        runtime = root / "runtime"
        if not runtime.is_dir():
            runtime = root / ".venv" / "Scripts"
        required = (
            runtime / "python.exe",
            runtime / "pythonw.exe",
            root / "native" / "credential_provider_safepckids" / "SafePCKidsCredentialProvider.dll",
            root / "scripts" / "Ativar-Desbloqueio-No-Boot.ps1",
            root / "models" / "face_detection_yunet_2023mar.onnx",
            root / "models" / "face_recognition_sface_2021dec.onnx",
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            return False, "Componentes necessarios ausentes: " + ", ".join(missing)

    notify("Criando diretorios protegidos do sistema...", 15)
    try:
        PROGRAMDATA_DIR.mkdir(parents=True, exist_ok=True)
        SECURITY_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, f"Nao foi possivel criar os diretorios do SafePCKids: {e}"

    dll_source = root / "native" / "credential_provider_safepckids" / "SafePCKidsCredentialProvider.dll"
    dll_target = provider_dll(root)

    notify("Configurando credencial segura DPAPI...", 30)
    secret = filhos_password or ""

    notify("Copiando driver de desbloqueio facial (DLL)...", 45)
    try:
        if sys.platform == "win32" and dll_source != dll_target:
            shutil.copy2(dll_source, dll_target)
    except Exception as e:
        return False, f"Nao foi possivel instalar a DLL de login facial: {e}"

    notify("Configurando PIN mestre dos pais e banco de dados...", 60)
    try:
        store = Storage(DEFAULT_DB_FILE)
        if master_pin and not store.get_setting("parent_pin_v1"):
            hashed = hash_pin(master_pin)
            store.set_setting("parent_pin_v1", hashed)

        if first_child_name and first_child_name.strip():
            existing_people = store.people()
            if not any(p[1].lower() == first_child_name.strip().lower() for p in existing_people):
                store.add_person(first_child_name.strip(), first_child_daily_limit_minutes)
        store.close()
    except Exception as e:
        return False, f"Nao foi possivel preparar o PIN e o banco de dados: {e}"

    notify("Configurando politicas de inatividade e servicos...", 75)
    try:
        if not CONFIG_FILE.exists():
            default_settings = {
                "inactivity_lock_enabled": False,
                "inactivity_lock_seconds": 0,
                "inactivity_warn_seconds": 0,
                "face_check_interval_seconds": 60,
                "description": "SafePCKids - Pausa automatica no bloqueio do Windows e verificacao silenciosa de troca de perfil"
            }
            CONFIG_FILE.write_text(json.dumps(default_settings, indent=2), encoding="utf-8")
    except Exception as e:
        return False, f"Nao foi possivel salvar as configuracoes: {e}"

    # Provisionamento do Windows: usuario local, servicos/tarefas e atalhos
    notify("Ativando servicos e integracoes do Windows...", 85)
    if sys.platform == "win32":
        ok, msg = ensure_filhos_windows_user(secret, username=filhos_username, preserve_existing=True)
        if not ok:
            return False, msg
        if defer_services:
            notify("Conta Filhos pronta. Cadastre o rosto para concluir.", 85)
            return True, "Conta Filhos preparada. Aguardando cadastro facial."
        ok, msg = setup_windows_services(root)
        if not ok:
            return False, msg
        health = verify_runtime_health()
        if not all((
            health["auth_service"]["registered"],
            health["filhos_agent"]["registered"],
            health["boot_auth"]["registered"],
            health["credential_provider"]["registered"],
            health["filhos_user"]["exists"],
        )):
            return False, f"Instalacao incompleta; verificacao dos componentes falhou: {health}"
        pipe_path = r"\\.\pipe\SafePCKidsAuthPipe"
        for _ in range(60):
            if os.path.exists(pipe_path):
                break
            time.sleep(0.5)
        else:
            return False, "O autenticador facial nao abriu o canal de login do Windows."
        try:
            create_desktop_shortcuts(root)
        except Exception as e:
            return False, str(e)

    marker_staging = INSTALL_MARKER.with_suffix(".tmp")
    marker_staging.write_text(json.dumps({"version": 1, "root": str(root)}), encoding="utf-8")
    marker_staging.replace(INSTALL_MARKER)

    notify("Instalacao concluida com sucesso!", 100)
    return True, "SafePCKids instalado e pronto para uso."
