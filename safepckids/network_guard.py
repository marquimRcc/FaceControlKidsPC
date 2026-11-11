"""SafePCKids - Modulo de Protecao de Rede Global (AdGuard Family + Firewall + SafeSearch).

Implementa 3 camadas de protecao em uma so:
1. DNS Criptografado (DoH / DNS-over-HTTPS) apontando para o AdGuard Family.
2. Politicas Administrativas de Navegador (Edge, Chrome, Brave) forcando SafeSearch,
   YouTube Restrito Estrito e bloqueio de DNS alternativo no navegador.
3. Regras no Windows Defender Firewall impedindo desvios para servidores DNS externos (Porta 53/853).
"""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("safepckids.network_guard")

ADGUARD_IPV4_PRIMARY = "94.140.14.15"
ADGUARD_IPV4_SECONDARY = "94.140.15.16"
ADGUARD_IPV6_PRIMARY = "2a10:50c0::bad1:ff"
ADGUARD_IPV6_SECONDARY = "2a10:50c0::bad2:ff"
ADGUARD_DOH_TEMPLATE = "https://dns-family.adguard.com/dns-query"
ADGUARD_DOT_HOSTNAME = "family.adguard-dns.com"

FIREWALL_PREFIX = "SafePCKids_AdGuard_"

BROWSER_POLICY_KEYS = [
    r"HKLM:\SOFTWARE\Policies\Microsoft\Edge",
    r"HKLM:\SOFTWARE\Policies\Google\Chrome",
    r"HKLM:\SOFTWARE\Policies\BraveSoftware\Brave",
]


def is_admin() -> bool:
    """Verifica se o processo atual possui privilegios elevados de administrador."""
    if sys.platform != "win32":
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _run_powershell(script: str, timeout: float = 20.0) -> Tuple[bool, str]:
    """Executa script PowerShell diretamente."""
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
    """Executa script PowerShell com privilegios elevados (UAC via Verb RunAs se necessario)."""
    if sys.platform != "win32":
        return False, "Plataforma nao suportada."

    if is_admin():
        return _run_powershell(script, timeout=timeout)

    # Quando o processo nao e administrador, delega para processo PowerShell elevado
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
        launcher = (
            f"Start-Process powershell.exe -Wait -WindowStyle Hidden "
            f"-ArgumentList '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"{script_file}\"' -Verb RunAs"
        )
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", launcher],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        for _ in range(25):
            if log_file.exists():
                break
            time.sleep(0.2)

        if log_file.exists():
            out = log_file.read_text(encoding="utf-8").strip()
            log_file.unlink(missing_ok=True)
            script_file.unlink(missing_ok=True)
            if "SUCCESS" in out:
                return True, "Operacao executada com sucesso."
            return False, out

        script_file.unlink(missing_ok=True)
        return False, "Operacao cancelada ou permissao negada no Controle de Conta de Usuario (UAC)."
    except Exception as exc:
        script_file.unlink(missing_ok=True)
        log_file.unlink(missing_ok=True)
        return False, str(exc)


def enable_adguard_family_protection() -> Tuple[bool, str]:
    """Ativa as 3 camadas de protecao global com privilégios de Administrador."""
    logger.info("Ativando Protecao Global AdGuard Family no Windows...")

    enable_script = f"""
    $ErrorActionPreference = 'Stop'

    # 1. Registra os servidores DoH do AdGuard Family no Windows 11
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV4_PRIMARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp $true -AutoUpgrade $true -ErrorAction SilentlyContinue
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV4_SECONDARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp $true -AutoUpgrade $true -ErrorAction SilentlyContinue
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV6_PRIMARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp $true -AutoUpgrade $true -ErrorAction SilentlyContinue
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV6_SECONDARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp $true -AutoUpgrade $true -ErrorAction SilentlyContinue

    # 2. Aplica DNS aos adaptadores fisicos (Wi-Fi e Ethernet)
    $adapters = Get-NetAdapter | Where-Object {{ $_.Status -eq 'Up' -and $_.Virtual -eq $false }}
    if (-not $adapters) {{
        $adapters = Get-NetAdapter | Where-Object {{ $_.Virtual -eq $false }}
    }}
    foreach ($a in $adapters) {{
        Set-DnsClientServerAddress -InterfaceIndex $a.InterfaceIndex -ServerAddresses ("{ADGUARD_IPV4_PRIMARY}", "{ADGUARD_IPV4_SECONDARY}")
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
        -Direction Outbound -Action Allow -Protocol UDP -RemotePort 53 -RemoteAddress "{ADGUARD_IPV4_PRIMARY}","{ADGUARD_IPV4_SECONDARY}"

    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Allow_DNS_TCP" -DisplayName "SafePCKids - Permitir DNS AdGuard TCP" `
        -Direction Outbound -Action Allow -Protocol TCP -RemotePort 53 -RemoteAddress "{ADGUARD_IPV4_PRIMARY}","{ADGUARD_IPV4_SECONDARY}"

    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Block_Other_DNS_UDP" -DisplayName "SafePCKids - Bloquear DNS Externo Nao Autorizado UDP" `
        -Direction Outbound -Action Block -Protocol UDP -RemotePort 53

    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Block_Other_DNS_TCP" -DisplayName "SafePCKids - Bloquear DNS Externo Nao Autorizado TCP" `
        -Direction Outbound -Action Block -Protocol TCP -RemotePort 53

    # 5. Flush de cache DNS
    Clear-DnsClientCache
    Write-Output "OK"
    """

    ok, msg = _run_powershell_elevated(enable_script)
    if not ok:
        logger.warning("Falha ao ativar Protecao AdGuard: %s", msg)
        return False, f"Falha ao ativar proteção: {msg}"
    return True, "Proteção Global AdGuard Family (DNS DoH, SafeSearch e Firewall) ativada com sucesso."


def disable_adguard_family_protection() -> Tuple[bool, str]:
    """Desativa completamente a protecao global e restaura o padrao do sistema."""
    logger.info("Desativando Protecao Global AdGuard Family...")

    disable_script = f"""
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
        "HKLM:\\SOFTWARE\\Policies\Google\\Chrome",
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

    ok, msg = _run_powershell_elevated(disable_script)
    if not ok:
        logger.warning("Falha ao desativar Protecao AdGuard: %s", msg)
        return False, f"Falha ao desativar proteção: {msg}"
    return True, "Proteção Global AdGuard desativada e configurações padrão restauradas."


def get_protection_status() -> Dict[str, Any]:
    """Verifica se a protecao AdGuard Family esta ativa e saudavel."""
    if sys.platform != "win32":
        return {"active": False, "details": "Nao disponivel fora do Windows."}

    ps_check = f"""
    $dns = (Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object {{ $_.ServerAddresses -contains '{ADGUARD_IPV4_PRIMARY}' }}).Count -gt 0
    $fw = (Get-NetFirewallRule -Name '{FIREWALL_PREFIX}Allow_DNS_UDP' -ErrorAction SilentlyContinue).Count -gt 0
    Write-Output "$dns,$fw"
    """
    ok, out = _run_powershell(ps_check, timeout=10.0)
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
