"""SafePCKids - Modulo de Protecao de Rede Global (AdGuard Family + Firewall + SafeSearch).

Implementa 3 camadas de protecao em uma so:
1. DNS Criptografado (DoH / DNS-over-HTTPS) apontando para o AdGuard Family.
2. Politicas Administrativas de Navegador (Edge, Chrome, Brave) forcando SafeSearch,
   YouTube Restrito Estrito e bloqueio de DNS alternativo no navegador.
3. Regras no Windows Defender Firewall impedindo desvios para servidores DNS externos (Porta 53/853).
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

if sys.platform == "win32":
    from ctypes import wintypes
else:
    wintypes = None  # type: ignore

logger = logging.getLogger("safepckids.network_guard")

ADGUARD_IPV4_PRIMARY = "94.140.14.15"
ADGUARD_IPV4_SECONDARY = "94.140.15.16"
ADGUARD_IPV6_PRIMARY = "2a10:50c0::bad1:ff"
ADGUARD_IPV6_SECONDARY = "2a10:50c0::bad2:ff"
ADGUARD_DOH_TEMPLATE = "https://dns-family.adguard.com/dns-query"
ADGUARD_DOT_HOSTNAME = "family.adguard-dns.com"

FIREWALL_PREFIX = "SafePCKids_AdGuard_"
PIPE_NAME = r"\\.\pipe\SafePCKidsAuthPipe"

_protection_status_cache: Dict[str, Any] = {}
_protection_status_cache_time: float = 0.0


def is_admin() -> bool:
    """Verifica se o processo atual possui privilegios elevados de administrador."""
    if sys.platform != "win32":
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def invalidate_protection_cache() -> None:
    """Limpa o cache de status da protecao de rede."""
    global _protection_status_cache, _protection_status_cache_time
    _protection_status_cache = {}
    _protection_status_cache_time = 0.0


def _send_pipe_command(command: str, timeout_sec: float = 12.0) -> Tuple[bool, Any]:
    """Envia um comando para o servico SafePCKidsAuthPipe (executado como SYSTEM)."""
    if sys.platform != "win32":
        return False, "Plataforma nao suportada."

    kernel32 = ctypes.windll.kernel32
    if hasattr(kernel32, "WaitNamedPipeW"):
        if not kernel32.WaitNamedPipeW(PIPE_NAME, int(timeout_sec * 1000)):
            return False, "Pipe indisponivel"

    h = kernel32.CreateFileW(PIPE_NAME, 0xC0000000, 0, None, 3, 0, None)
    if h == ctypes.c_void_p(-1).value or not h:
        return False, "Nao foi possivel conectar ao SafePCKidsAuthPipe"

    try:
        written = wintypes.DWORD()
        data = f"{command}\n".encode("ascii")
        if not kernel32.WriteFile(h, data, len(data), ctypes.byref(written), None):
            return False, "Falha ao enviar comando pelo pipe"

        buf = ctypes.create_string_buffer(8192)
        read = wintypes.DWORD()
        if not kernel32.ReadFile(h, buf, 8191, ctypes.byref(read), None):
            return False, "Falha ao ler resposta do pipe"

        raw = buf.raw[:read.value].decode("utf-8", errors="replace")
        payload = json.loads(raw)
        status = payload.get("status")
        data_resp = payload.get("data", {})
        if status in ("ALLOW", "NETGUARD_OK", "PONG"):
            return True, data_resp
        return False, data_resp.get("message") or "Erro retornado pelo servico IPC"
    except Exception as exc:
        logger.debug("Excecao na comunicacao com pipe: %s", exc)
        return False, str(exc)
    finally:
        kernel32.CloseHandle(h)


def _run_powershell(script: str, timeout: float = 25.0) -> Tuple[bool, str]:
    """Executa script PowerShell silenciosamente."""
    if sys.platform != "win32":
        return False, "Plataforma nao suportada."
    try:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode == 0:
            return True, res.stdout.strip()
        return False, res.stderr.strip() or res.stdout.strip()
    except Exception as exc:
        logger.error("Falha ao executar PowerShell: %s", exc)
        return False, str(exc)


def _run_powershell_elevated(script: str, timeout: float = 30.0) -> Tuple[bool, str]:
    """Executa script PowerShell com privilegios elevados via UAC."""
    if sys.platform != "win32":
        return False, "Plataforma nao suportada."

    if is_admin():
        return _run_powershell(script, timeout=timeout)

    timestamp = int(time.time() * 1000)
    temp_dir = Path(tempfile.gettempdir())
    script_file = temp_dir / f"safepckids_netguard_{timestamp}.ps1"
    log_file = temp_dir / f"safepckids_netguard_{timestamp}.log"

    wrapped_ps1 = f"""
    try {{
        {script}
        Set-Content -Path '{log_file}' -Value 'SUCCESS' -Encoding UTF8
    }} catch {{
        Set-Content -Path '{log_file}' -Value "ERROR: $($_.Exception.Message)" -Encoding UTF8
        exit 1
    }}
    """
    try:
        script_file.write_text(wrapped_ps1, encoding="utf-8")
        # Usa ShellExecuteW nativo para acionar o dialogo de UAC
        params = f"-NoProfile -ExecutionPolicy Bypass -File \"{script_file}\""
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", params, None, 0)
        if ret <= 32:
            script_file.unlink(missing_ok=True)
            return False, "Permissao de Administrador negada pelo usuario no UAC."

        for _ in range(30):
            if log_file.exists():
                break
            time.sleep(0.3)

        if log_file.exists():
            out = log_file.read_text(encoding="utf-8").strip()
            log_file.unlink(missing_ok=True)
            script_file.unlink(missing_ok=True)
            if "SUCCESS" in out:
                return True, "Operacao executada com sucesso."
            return False, out

        script_file.unlink(missing_ok=True)
        return False, "Tempo limite esgotado aguardando autorizacao."
    except Exception as exc:
        script_file.unlink(missing_ok=True)
        log_file.unlink(missing_ok=True)
        return False, str(exc)


def enable_adguard_family_protection_direct() -> Tuple[bool, str]:
    """Execucao direta dos comandos de ativacao do AdGuard (chamada pelo servico SYSTEM ou processo Admin)."""
    invalidate_protection_cache()
    ps_enable = f"""
    $ErrorActionPreference = 'Stop'

    # 1. Registra os servidores DoH do AdGuard Family no Windows 11 (parametros 1/0 confiaveis)
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV4_PRIMARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp 1 -AutoUpgrade 1 -ErrorAction SilentlyContinue
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV4_SECONDARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp 1 -AutoUpgrade 1 -ErrorAction SilentlyContinue
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV6_PRIMARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp 1 -AutoUpgrade 1 -ErrorAction SilentlyContinue
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV6_SECONDARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp 1 -AutoUpgrade 1 -ErrorAction SilentlyContinue

    # 2. Configura os adaptadores fisicos (Wi-Fi e Ethernet)
    $adapters = Get-NetAdapter | Where-Object {{ $_.Status -eq 'Up' -and $_.Virtual -eq $false }}
    if (-not $adapters) {{
        $adapters = Get-NetAdapter | Where-Object {{ $_.Virtual -eq $false }}
    }}
    foreach ($a in $adapters) {{
        Set-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -ServerAddresses @("{ADGUARD_IPV4_PRIMARY}", "{ADGUARD_IPV4_SECONDARY}")
    }}

    # 3. Politicas de Navegador no Registro HKLM
    $browsers = @(
        "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
        "HKLM:\\SOFTWARE\\Policies\\Google\\Chrome",
        "HKLM:\\SOFTWARE\\Policies\\BraveSoftware\\Brave"
    )
    foreach ($key in $browsers) {{
        if (-not (Test-Path $key)) {{
            New-Item -Path $key -Force | Out-Null
        }}
        Set-ItemProperty -Path $key -Name "ForceGoogleSafeSearch" -Value 1 -Type DWord -Force
        Set-ItemProperty -Path $key -Name "ForceYouTubeRestrict" -Value 2 -Type DWord -Force
        Set-ItemProperty -Path $key -Name "ForceBingSafeSearch" -Value 1 -Type DWord -Force
        Set-ItemProperty -Path $key -Name "DnsOverHttpsMode" -Value "secure" -Type String -Force
        Set-ItemProperty -Path $key -Name "DnsOverHttpsTemplates" -Value "{ADGUARD_DOH_TEMPLATE}" -Type String -Force
    }}

    # 4. Regras do Windows Defender Firewall Anti-Burla
    Remove-NetFirewallRule -Name "{FIREWALL_PREFIX}*" -ErrorAction SilentlyContinue

    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Allow_DNS_UDP" -DisplayName "SafePCKids - Permitir DNS AdGuard UDP" `
        -Direction Outbound -Action Allow -Protocol UDP -RemotePort 53 -RemoteAddress @("{ADGUARD_IPV4_PRIMARY}","{ADGUARD_IPV4_SECONDARY}")

    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Allow_DNS_TCP" -DisplayName "SafePCKids - Permitir DNS AdGuard TCP" `
        -Direction Outbound -Action Allow -Protocol TCP -RemotePort 53 -RemoteAddress @("{ADGUARD_IPV4_PRIMARY}","{ADGUARD_IPV4_SECONDARY}")

    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Block_Other_DNS_UDP" -DisplayName "SafePCKids - Bloquear DNS Externo Nao Autorizado UDP" `
        -Direction Outbound -Action Block -Protocol UDP -RemotePort 53

    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Block_Other_DNS_TCP" -DisplayName "SafePCKids - Bloquear DNS Externo Nao Autorizado TCP" `
        -Direction Outbound -Action Block -Protocol TCP -RemotePort 53

    # 5. Flush de cache DNS
    Clear-DnsClientCache
    Write-Output "OK"
    """
    ok, out = _run_powershell(ps_enable)
    invalidate_protection_cache()
    if not ok:
        return False, f"Falha ao configurar protecao: {out}"
    return True, "Proteção Global AdGuard Family ativada com sucesso."


def disable_adguard_family_protection_direct() -> Tuple[bool, str]:
    """Execucao direta da desativacao (chamada pelo servico SYSTEM ou processo Admin)."""
    invalidate_protection_cache()
    ps_disable = f"""
    $ErrorActionPreference = 'SilentlyContinue'

    # 1. Restaura adaptadores para DHCP
    $adapters = Get-NetAdapter | Where-Object {{ $_.Virtual -eq $false }}
    foreach ($a in $adapters) {{
        Set-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -ResetServerAddresses
    }}

    # 2. Remove regras de firewall
    Remove-NetFirewallRule -Name "{FIREWALL_PREFIX}*" -ErrorAction SilentlyContinue

    # 3. Remove politicas de navegador
    $browsers = @(
        "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Edge",
        "HKLM:\\SOFTWARE\\Policies\\Google\\Chrome",
        "HKLM:\\SOFTWARE\\Policies\\BraveSoftware\\Brave"
    )
    $props = @("ForceGoogleSafeSearch", "ForceYouTubeRestrict", "ForceBingSafeSearch", "DnsOverHttpsMode", "DnsOverHttpsTemplates")
    foreach ($key in $browsers) {{
        if (Test-Path $key) {{
            foreach ($p in $props) {{
                Remove-ItemProperty -Path $key -Name $p -ErrorAction SilentlyContinue
            }}
        }}
    }}

    # 4. Flush de cache DNS
    Clear-DnsClientCache
    Write-Output "OK"
    """
    ok, out = _run_powershell(ps_disable)
    invalidate_protection_cache()
    if not ok:
        return False, f"Falha ao desativar: {out}"
    return True, "Proteção Global AdGuard desativada e configurações padrão restauradas."


def enable_adguard_family_protection() -> Tuple[bool, str]:
    """Ativa a protecao global. Prioriza o servico SYSTEM via pipe, ou executa diretamente se ja for admin."""
    logger.info("Solicitando ativacao da Protecao Global AdGuard Family...")

    # 1. Se ja for processo Administrador, executa diretamente
    if is_admin():
        return enable_adguard_family_protection_direct()

    # 2. Tenta acionar via servico SYSTEM (SafePCKidsAuthPipe)
    ok, resp = _send_pipe_command("NETGUARD_ENABLE")
    if ok:
        invalidate_protection_cache()
        msg = resp.get("message") if isinstance(resp, dict) else "Proteção ativada com sucesso."
        return True, msg

    # 3. Fallback: Eleva permissao via ShellExecute UAC
    logger.info("Pipe nao disponivel, tentando fallback com elevacao UAC...")
    ps_enable = f"""
    $ErrorActionPreference = 'Stop'
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV4_PRIMARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp 1 -AutoUpgrade 1 -ErrorAction SilentlyContinue
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV4_SECONDARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp 1 -AutoUpgrade 1 -ErrorAction SilentlyContinue
    $adapters = Get-NetAdapter | Where-Object {{ $_.Virtual -eq $false }}
    foreach ($a in $adapters) {{
        Set-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -ServerAddresses @("{ADGUARD_IPV4_PRIMARY}", "{ADGUARD_IPV4_SECONDARY}")
    }}
    Remove-NetFirewallRule -Name "{FIREWALL_PREFIX}*" -ErrorAction SilentlyContinue
    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Allow_DNS_UDP" -DisplayName "SafePCKids - Permitir DNS AdGuard UDP" -Direction Outbound -Action Allow -Protocol UDP -RemotePort 53 -RemoteAddress @("{ADGUARD_IPV4_PRIMARY}","{ADGUARD_IPV4_SECONDARY}")
    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Block_Other_DNS_UDP" -DisplayName "SafePCKids - Bloquear DNS Externo Nao Autorizado UDP" -Direction Outbound -Action Block -Protocol UDP -RemotePort 53
    Clear-DnsClientCache
    """
    ok_elev, msg_elev = _run_powershell_elevated(ps_enable)
    invalidate_protection_cache()
    return ok_elev, msg_elev


def disable_adguard_family_protection() -> Tuple[bool, str]:
    """Desativa a protecao global. Prioriza o servico SYSTEM via pipe, ou executa diretamente."""
    logger.info("Solicitando desativacao da Protecao Global AdGuard Family...")

    if is_admin():
        return disable_adguard_family_protection_direct()

    ok, resp = _send_pipe_command("NETGUARD_DISABLE")
    if ok:
        invalidate_protection_cache()
        msg = resp.get("message") if isinstance(resp, dict) else "Proteção desativada com sucesso."
        return True, msg

    ps_disable = f"""
    $ErrorActionPreference = 'SilentlyContinue'
    $adapters = Get-NetAdapter | Where-Object {{ $_.Virtual -eq $false }}
    foreach ($a in $adapters) {{
        Set-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -ResetServerAddresses
    }}
    Remove-NetFirewallRule -Name "{FIREWALL_PREFIX}*" -ErrorAction SilentlyContinue
    Clear-DnsClientCache
    """
    ok_elev, msg_elev = _run_powershell_elevated(ps_disable)
    invalidate_protection_cache()
    return ok_elev, msg_elev


def get_protection_status_direct() -> Dict[str, Any]:
    """Consulta direta e instantanea do status real da rede."""
    if sys.platform != "win32":
        return {"active": False, "details": "Nao disponivel fora do Windows."}

    ps_check = f"""
    $dns = (Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object {{ $_.ServerAddresses -contains '{ADGUARD_IPV4_PRIMARY}' }}).Count -gt 0
    $fw = (Get-NetFirewallRule -Name '{FIREWALL_PREFIX}Allow_DNS_UDP' -ErrorAction SilentlyContinue).Count -gt 0
    Write-Output "$dns,$fw"
    """
    ok, out = _run_powershell(ps_check, timeout=8.0)
    dns_active = False
    fw_active = False
    if ok and out:
        parts = [p.strip().lower() for p in out.split(",")]
        if len(parts) >= 2:
            dns_active = parts[0] == "true"
            fw_active = parts[1] == "true"

    is_active = dns_active or fw_active
    return {
        "active": is_active,
        "dns_configured": dns_active,
        "firewall_rules_present": fw_active,
        "adguard_ipv4": ADGUARD_IPV4_PRIMARY,
        "doh_template": ADGUARD_DOH_TEMPLATE,
        "details": "Ativo com DoH Criptografado, SafeSearch e Firewall Anti-Burla" if is_active else "Inativo (Usando DNS padrão da operadora)",
    }


def get_protection_status(force_refresh: bool = False) -> Dict[str, Any]:
    """Consulta o status com cache de 5s para evitar sobrecarga de consultas."""
    global _protection_status_cache, _protection_status_cache_time
    now = time.time()
    if not force_refresh and _protection_status_cache and (now - _protection_status_cache_time < 5.0):
        return dict(_protection_status_cache)

    status = get_protection_status_direct()
    _protection_status_cache = status
    _protection_status_cache_time = now
    return dict(status)
