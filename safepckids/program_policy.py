"""SafePCKids - Politica e Controle de Acesso a Programas por Perfil.

Gerencia os programas permitidos/bloqueados para cada crianca cadastrada:
- Carga e persistencia de configuracoes em programas_inicializar.json
- Compatibilidade reversa com o formato anterior
- Consulta de programas liberados/bloqueados por perfil (child_id)
- Varredura e encerramento de processos em execucao na sessao de perfis com bloqueio ativo
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import signal
import sys
from typing import Optional

from .platform_paths import application_data_dir

logger = logging.getLogger("SafePCKidsProgramPolicy")

PROGRAMS_FILE = application_data_dir() / "programas_inicializar.json"


def default_programs_config() -> dict:
    return {
        "enabled": True,
        "description": "Lista de programas configurados e regras de acesso por perfil",
        "programs": [
            {
                "name": "Brave",
                "executable": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                "arguments": "",
                "enabled": True,
                "blocked_child_ids": [],
            }
        ],
    }


def normalize_child_id(child_id: int | str) -> int:
    try:
        return int(child_id)
    except (ValueError, TypeError):
        return -1


def normalize_program_entry(prog: dict) -> dict:
    """Garante chaves e tipos esperados no dicionario de um programa."""
    raw_blocked = prog.get("blocked_child_ids", [])
    if not isinstance(raw_blocked, (list, tuple, set)):
        raw_blocked = []

    blocked_ids: list[int] = []
    for item in raw_blocked:
        cid = normalize_child_id(item)
        if cid >= 0 and cid not in blocked_ids:
            blocked_ids.append(cid)

    prog["name"] = str(prog.get("name", "Programa")).strip()
    prog["executable"] = str(prog.get("executable", "")).strip()
    prog["arguments"] = str(prog.get("arguments", "")).strip()
    prog["enabled"] = bool(prog.get("enabled", True))
    prog["blocked_child_ids"] = blocked_ids
    return prog


def load_programs_config(config_path: Optional[Path] = None) -> dict:
    target_path = config_path or PROGRAMS_FILE
    default_cfg = default_programs_config()

    if not target_path.exists():
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(json.dumps(default_cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.debug("Falha ao criar arquivo padrao de programas: %s", e)
        return default_cfg

    try:
        data = json.loads(target_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default_cfg

        data.setdefault("enabled", True)
        data.setdefault("description", default_cfg["description"])
        raw_programs = data.get("programs", [])
        if not isinstance(raw_programs, list):
            raw_programs = []

        normalized_programs = []
        for p in raw_programs:
            if isinstance(p, dict):
                normalized_programs.append(normalize_program_entry(p))

        data["programs"] = normalized_programs
        return data
    except Exception as e:
        logger.warning("Falha ao carregar configuracao de programas de %s: %s", target_path, e)
        return default_cfg


def save_programs_config(config_data: dict, config_path: Optional[Path] = None) -> bool:
    target_path = config_path or PROGRAMS_FILE
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # Normaliza antes de salvar
        programs = config_data.get("programs", [])
        if isinstance(programs, list):
            config_data["programs"] = [normalize_program_entry(p) for p in programs if isinstance(p, dict)]
        target_path.write_text(json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as e:
        logger.error("Falha ao salvar configuracao de programas em %s: %s", target_path, e)
        return False


def is_program_allowed_for_child(program: dict, child_id: int | str) -> bool:
    cid = normalize_child_id(child_id)
    if cid < 0:
        return True
    blocked_ids = [normalize_child_id(x) for x in program.get("blocked_child_ids", [])]
    return cid not in blocked_ids


def set_program_allowed_for_child(program: dict, child_id: int | str, allowed: bool) -> None:
    cid = normalize_child_id(child_id)
    if cid < 0:
        return
    blocked_ids = [normalize_child_id(x) for x in program.get("blocked_child_ids", [])]
    if allowed:
        blocked_ids = [x for x in blocked_ids if x != cid]
    else:
        if cid not in blocked_ids:
            blocked_ids.append(cid)
    program["blocked_child_ids"] = blocked_ids


def get_blocked_programs_for_child(config_data: dict, child_id: int | str) -> list[dict]:
    cid = normalize_child_id(child_id)
    if cid < 0 or not config_data.get("enabled", False):
        return []
    programs = config_data.get("programs", [])
    return [p for p in programs if p.get("enabled", True) and not is_program_allowed_for_child(p, cid)]


def get_allowed_programs_for_child(config_data: dict, child_id: int | str) -> list[dict]:
    cid = normalize_child_id(child_id)
    if not config_data.get("enabled", False):
        return []
    programs = config_data.get("programs", [])
    return [p for p in programs if p.get("enabled", True) and is_program_allowed_for_child(p, cid)]


def extract_executable_names(program: dict) -> set[str]:
    """Retorna conjunto de nomes de executaveis em minusculas a partir de um programa cadastrado."""
    names = set()
    raw_exe = program.get("executable", "").strip()
    if raw_exe:
        names.add(Path(raw_exe).name.lower())

    extra = program.get("process_names", [])
    if isinstance(extra, (list, tuple)):
        for x in extra:
            if isinstance(x, str) and x.strip():
                names.add(Path(x.strip()).name.lower())

    # Tratamento especial de conveniencia para programas conhecidos se apenas o nome basico foi dado
    prog_name = program.get("name", "").strip().lower()
    if "roblox" in prog_name:
        names.add("robloxplayerbeta.exe")
        names.add("robloxplayerlauncher.exe")
    elif "minecraft" in prog_name:
        names.add("minecraft.exe")
        names.add("minecraftlauncher.exe")
        names.add("javaw.exe")

    return {n for n in names if n}


def find_and_terminate_blocked_processes(blocked_exe_names: set[str]) -> list[str]:
    """Varre processos ativos na sessao atual do usuario e encerra aqueles que coincidem com a lista de bloqueio.

    Retorna lista com os nomes dos executaveis que foram encerrados.
    """
    if not blocked_exe_names:
        return []

    targets = {exe.strip().lower() for exe in blocked_exe_names if exe.strip()}
    terminated: list[str] = []

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32

            my_pid = kernel32.GetCurrentProcessId()
            my_session = wintypes.DWORD()
            if not kernel32.ProcessIdToSessionId(my_pid, ctypes.byref(my_session)):
                return []

            TH32CS_SNAPPROCESS = 0x00000002
            PROCESS_TERMINATE = 0x0001

            class PROCESSENTRY32W(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes.DWORD),
                    ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260),
                ]

            h_snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
            if h_snap == ctypes.c_void_p(-1).value:
                return []

            try:
                pe = PROCESSENTRY32W()
                pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                if not kernel32.Process32FirstW(h_snap, ctypes.byref(pe)):
                    return []

                proc_session = wintypes.DWORD()
                while True:
                    exe_file = pe.szExeFile.lower()
                    if exe_file in targets and pe.th32ProcessID != my_pid:
                        if kernel32.ProcessIdToSessionId(pe.th32ProcessID, ctypes.byref(proc_session)):
                            if proc_session.value == my_session.value:
                                h_proc = kernel32.OpenProcess(PROCESS_TERMINATE, False, pe.th32ProcessID)
                                if h_proc:
                                    try:
                                        if kernel32.TerminateProcess(h_proc, 1):
                                            logger.info("Processo bloqueado encerrado: PID %s (%s)", pe.th32ProcessID, pe.szExeFile)
                                            terminated.append(pe.szExeFile)
                                    finally:
                                        kernel32.CloseHandle(h_proc)
                    if not kernel32.Process32NextW(h_snap, ctypes.byref(pe)):
                        break
            finally:
                kernel32.CloseHandle(h_snap)
        except Exception as e:
            logger.debug("Falha na inspecao de processos bloqueados Windows: %s", e)
    else:
        try:
            for pid_dir in Path("/proc").glob("[0-9]*"):
                comm_file = pid_dir / "comm"
                if comm_file.exists():
                    try:
                        comm_name = comm_file.read_text(encoding="utf-8").strip().lower()
                        if comm_name in targets:
                            pid = int(pid_dir.name)
                            os.kill(pid, signal.SIGTERM)
                            logger.info("Processo bloqueado encerrado: PID %s (%s)", pid, comm_name)
                            terminated.append(comm_name)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("Falha na inspecao de processos bloqueados Linux: %s", e)

    return terminated


def enforce_child_process_restrictions(
    child_id: int | str,
    child_name: str,
    config_path: Optional[Path] = None,
) -> list[str]:
    """Verifica e encerra processos bloqueados para a crianca na sessao atual.

    Retorna a lista de nomes amigaveis dos programas que foram encerrados.
    """
    cfg = load_programs_config(config_path)
    if not cfg.get("enabled", True):
        return []

    blocked = get_blocked_programs_for_child(cfg, child_id)
    if not blocked:
        return []

    all_blocked_exe_names: set[str] = set()
    prog_by_exe: dict[str, str] = {}
    for p in blocked:
        p_name = p.get("name", "Programa")
        exes = extract_executable_names(p)
        for exe in exes:
            all_blocked_exe_names.add(exe)
            prog_by_exe[exe.lower()] = p_name

    terminated = find_and_terminate_blocked_processes(all_blocked_exe_names)
    display_names: list[str] = []
    for t in terminated:
        friendly = prog_by_exe.get(t.lower(), t)
        if friendly not in display_names:
            display_names.append(friendly)

    if display_names:
        logger.warning(
            "Programas bloqueados encerrados para %s (ID %s): %s",
            child_name,
            child_id,
            ", ".join(display_names),
        )

    return display_names


def discover_installed_programs() -> list[dict]:
    """Descobre automaticamente jogos, navegadores e programas instalados no computador.

    Retorna lista de dicionarios: [{"name": str, "executable": str, "arguments": "", "enabled": True, "blocked_child_ids": []}]
    """
    found: dict[str, str] = {}
    import glob

    # 1. Padroes diretos de jogos, navegadores e launchers conhecidos
    known_patterns = [
        ("Roblox", r"C:\Users\*\AppData\Local\Roblox\Versions\*\RobloxPlayerBeta.exe"),
        ("Minecraft Launcher", r"C:\Program Files (x86)\Minecraft Launcher\MinecraftLauncher.exe"),
        ("Minecraft Launcher", r"C:\Program Files\Minecraft Launcher\MinecraftLauncher.exe"),
        ("Steam", r"C:\Program Files (x86)\Steam\steam.exe"),
        ("Steam", r"C:\Program Files\Steam\steam.exe"),
        ("Brave", r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ("Google Chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        ("Google Chrome", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        ("Microsoft Edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        ("Stremio", r"C:\Users\*\AppData\Local\Programs\LNV\Stremio-4\stremio.exe"),
        ("BlueStacks", r"C:\Program Files\BlueStacks_nxt\HD-Player.exe"),
        ("Epic Games", r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe"),
        ("Discord", r"C:\Users\*\AppData\Local\Discord\app-*\Discord.exe"),
    ]
    for name, pattern in known_patterns:
        for match in glob.glob(pattern):
            if Path(match).is_file() and name not in found:
                found[name] = match

    # 2. Varredura no Registro do Windows (Uninstall)
    if sys.platform == "win32":
        try:
            import winreg

            hives = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            ]
            skip_terms = {
                "update", "redistributable", "runtime", "driver", "security", "package",
                "kb", "windows", "sdk", "installer", "amd", "nvidia", "intel", "directx",
                "visual c++", "framework", "chipset", "crashhandler",
            }
            for hive, subpath in hives:
                try:
                    k = winreg.OpenKey(hive, subpath)
                    for i in range(winreg.QueryInfoKey(k)[0]):
                        try:
                            sk = winreg.OpenKey(k, winreg.EnumKey(k, i))
                            dn = winreg.QueryValueEx(sk, "DisplayName")[0].strip()
                            dn_lower = dn.lower()
                            if not dn or any(s in dn_lower for s in skip_terms):
                                continue

                            exe = None
                            try:
                                raw_icon = winreg.QueryValueEx(sk, "DisplayIcon")[0].split(",")[0].strip('"\' ')
                                if raw_icon.lower().endswith(".exe") and Path(raw_icon).is_file():
                                    cand_lower = Path(raw_icon).name.lower()
                                    if "unins" not in cand_lower and "setup" not in cand_lower:
                                        exe = raw_icon
                            except Exception:
                                pass

                            if not exe:
                                try:
                                    loc = winreg.QueryValueEx(sk, "InstallLocation")[0].strip('"\' ')
                                    if loc and Path(loc).is_dir():
                                        for cand in Path(loc).glob("*.exe"):
                                            cand_lower = cand.name.lower()
                                            if "unins" not in cand_lower and "setup" not in cand_lower:
                                                exe = str(cand)
                                                break
                                except Exception:
                                    pass

                            if exe:
                                clean_name = dn
                                if "roblox" in dn_lower and "studio" not in dn_lower:
                                    clean_name = "Roblox"
                                if clean_name not in found:
                                    found[clean_name] = exe
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as e:
            logger.debug("Falha ao varrer registro para programas instalados: %s", e)

    results: list[dict] = []
    for name, exe in sorted(found.items(), key=lambda x: x[0].lower()):
        results.append({
            "name": name,
            "executable": exe,
            "arguments": "",
            "enabled": True,
            "blocked_child_ids": [],
        })

    return results


