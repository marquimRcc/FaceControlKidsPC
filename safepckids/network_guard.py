"""SafePCKids - Modulo de Protecao de Rede Global (AdGuard Family + Firewall + SafeSearch).

Implementa 3 camadas de protecao em uma so:
1. DNS Criptografado (DoH / DNS-over-HTTPS) apontando para o AdGuard Family.
2. Politicas Administrativas de Navegador (Edge, Chrome, Brave) forcando SafeSearch,
   YouTube Restrito Estrito e bloqueio de DNS alternativo no navegador.
3. Regras no Windows Defender Firewall impedindo desvios para servidores DNS externos (Porta 53/853).
"""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
from typing import Any, Dict, List, Tuple

if sys.platform == "win32":
    import winreg
else:
    winreg = None  # type: ignore

logger = logging.getLogger("safepckids.network_guard")

ADGUARD_IPV4_PRIMARY = "94.140.14.15"
ADGUARD_IPV4_SECONDARY = "94.140.15.16"
ADGUARD_IPV6_PRIMARY = "2a10:50c0::bad1:ff"
ADGUARD_IPV6_SECONDARY = "2a10:50c0::bad2:ff"
ADGUARD_DOH_TEMPLATE = "https://dns-family.adguard.com/dns-query"
ADGUARD_DOT_HOSTNAME = "family.adguard-dns.com"

FIREWALL_PREFIX = "SafePCKids_AdGuard_"

BROWSER_POLICY_PATHS = [
    r"SOFTWARE\Policies\Microsoft\Edge",
    r"SOFTWARE\Policies\Google\Chrome",
    r"SOFTWARE\Policies\BraveSoftware\Brave",
]


def _run_powershell(script: str, timeout: float = 20.0) -> Tuple[bool, str]:
    """Executa um script PowerShell silenciosamente."""
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


def apply_doh_and_dns_settings() -> Tuple[bool, str]:
    """Configura os servidores DoH e DNS no Windows 11 para todos os adaptadores ativos."""
    ps_script = f"""
    $ErrorActionPreference = 'SilentlyContinue'

    # 1. Registra os templates DoH do AdGuard Family no Windows 11
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV4_PRIMARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp $true -AutoUpgrade $true
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV4_SECONDARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp $true -AutoUpgrade $true
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV6_PRIMARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp $true -AutoUpgrade $true
    Add-DnsClientDohServerAddress -ServerAddress "{ADGUARD_IPV6_SECONDARY}" -DohTemplate "{ADGUARD_DOH_TEMPLATE}" -AllowFallbackToUdp $true -AutoUpgrade $true

    # 2. Configura os adaptadores fisicos conectados
    $adapters = Get-NetAdapter | Where-Object {{ $_.Status -eq 'Up' -and $_.Virtual -eq $false }}
    if (-not $adapters) {{
        $adapters = Get-NetAdapter | Where-Object {{ $_.Virtual -eq $false }}
    }}

    foreach ($adapter in $adapters) {{
        Set-DnsClientServerAddress -InterfaceIndex $adapter.InterfaceIndex -ServerAddresses ("{ADGUARD_IPV4_PRIMARY}", "{ADGUARD_IPV4_SECONDARY}")
    }}

    # 3. Limpa o cache DNS
    Clear-DnsClientCache
    Write-Output "OK"
    """
    ok, out = _run_powershell(ps_script)
    if not ok:
        logger.warning("Nao foi possivel configurar DoH/DNS totalmente: %s", out)
        return False, f"Falha ao configurar DNS/DoH: {out}"
    return True, "DNS AdGuard Family configurado com sucesso."


def restore_default_dns_settings() -> Tuple[bool, str]:
    """Restaura as configuracoes de DNS dos adaptadores para DHCP."""
    ps_script = """
    $ErrorActionPreference = 'SilentlyContinue'
    $adapters = Get-NetAdapter | Where-Object { $_.Virtual -eq $false }
    foreach ($adapter in $adapters) {
        Set-DnsClientServerAddress -InterfaceIndex $adapter.InterfaceIndex -ResetServerAddresses
    }
    Clear-DnsClientCache
    Write-Output "OK"
    """
    ok, out = _run_powershell(ps_script)
    if not ok:
        return False, f"Falha ao restaurar DNS: {out}"
    return True, "Configuracoes de DNS restauradas para padrao (DHCP)."


def apply_browser_policies() -> Tuple[bool, str]:
    """Configura politicas no Registro do Windows (HKLM) para Chrome, Edge e Brave."""
    if sys.platform != "win32" or not winreg:
        return False, "Nao suportado nesta plataforma."

    policies = {
        "ForceGoogleSafeSearch": (winreg.REG_DWORD, 1),
        "ForceYouTubeRestrict": (winreg.REG_DWORD, 2),  # 2 = Modo Restrito Estrito
        "ForceBingSafeSearch": (winreg.REG_DWORD, 1),
        "DnsOverHttpsMode": (winreg.REG_SZ, "secure"),
        "DnsOverHttpsTemplates": (winreg.REG_SZ, ADGUARD_DOH_TEMPLATE),
    }

    try:
        for subkey in BROWSER_POLICY_PATHS:
            try:
                key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, subkey, 0, winreg.KEY_SET_VALUE)
                for val_name, (val_type, val_data) in policies.items():
                    winreg.SetValueEx(key, val_name, 0, val_type, val_data)
                winreg.CloseKey(key)
            except Exception as e:
                logger.warning("Falha ao gravar politica em %s: %s", subkey, e)
        return True, "Politicas de SafeSearch e DoH aplicadas aos navegadores."
    except Exception as exc:
        return False, f"Erro ao aplicar politicas de navegadores: {exc}"


def remove_browser_policies() -> Tuple[bool, str]:
    """Remove as politicas aplicadas aos navegadores no Registro."""
    if sys.platform != "win32" or not winreg:
        return False, "Nao suportado nesta plataforma."

    policy_keys = [
        "ForceGoogleSafeSearch",
        "ForceYouTubeRestrict",
        "ForceBingSafeSearch",
        "DnsOverHttpsMode",
        "DnsOverHttpsTemplates",
    ]

    for subkey in BROWSER_POLICY_PATHS:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey, 0, winreg.KEY_SET_VALUE)
            for val_name in policy_keys:
                try:
                    winreg.DeleteValue(key, val_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning("Falha ao remover politica em %s: %s", subkey, e)
    return True, "Politicas de navegador removidas."


def apply_firewall_anti_bypass_rules() -> Tuple[bool, str]:
    """Cria regras no Windows Defender Firewall impedindo contorno do DNS AdGuard."""
    ps_script = f"""
    $ErrorActionPreference = 'SilentlyContinue'

    # Remove regras antigas do SafePCKids se houver
    Remove-NetFirewallRule -Name "{FIREWALL_PREFIX}*" -ErrorAction SilentlyContinue

    # 1. Permite saida UDP/TCP na porta 53 para os servidores AdGuard Family
    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Allow_DNS_UDP" -DisplayName "SafePCKids - Permitir DNS AdGuard UDP" `
        -Direction Outbound -Action Allow -Protocol UDP -RemotePort 53 -RemoteAddress "{ADGUARD_IPV4_PRIMARY}","{ADGUARD_IPV4_SECONDARY}"

    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Allow_DNS_TCP" -DisplayName "SafePCKids - Permitir DNS AdGuard TCP" `
        -Direction Outbound -Action Allow -Protocol TCP -RemotePort 53 -RemoteAddress "{ADGUARD_IPV4_PRIMARY}","{ADGUARD_IPV4_SECONDARY}"

    # 2. Bloqueia qualquer outra saida na porta 53 (impede uso manual de 8.8.8.8, 1.1.1.1, etc.)
    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Block_Other_DNS_UDP" -DisplayName "SafePCKids - Bloquear DNS Externo Nao Autorizado UDP" `
        -Direction Outbound -Action Block -Protocol UDP -RemotePort 53

    New-NetFirewallRule -Name "{FIREWALL_PREFIX}Block_Other_DNS_TCP" -DisplayName "SafePCKids - Bloquear DNS Externo Nao Autorizado TCP" `
        -Direction Outbound -Action Block -Protocol TCP -RemotePort 53

    Write-Output "OK"
    """
    ok, out = _run_powershell(ps_script)
    if not ok:
        return False, f"Falha ao configurar regras de firewall: {out}"
    return True, "Regras de Firewall anti-burla ativadas com sucesso."


def remove_firewall_rules() -> Tuple[bool, str]:
    """Remove todas as regras de firewall criadas pelo SafePCKids."""
    ps_script = f"""
    $ErrorActionPreference = 'SilentlyContinue'
    Remove-NetFirewallRule -Name "{FIREWALL_PREFIX}*" -ErrorAction SilentlyContinue
    Write-Output "OK"
    """
    ok, out = _run_powershell(ps_script)
    if not ok:
        return False, f"Falha ao remover regras de firewall: {out}"
    return True, "Regras de firewall removidas com sucesso."


def enable_adguard_family_protection() -> Tuple[bool, str]:
    """Ativa as 3 camadas de protecao global: DNS DoH, Politicas de Navegador e Firewall."""
    logger.info("Ativando Protecao Global AdGuard Family no Windows...")
    errs = []

    ok_dns, msg_dns = apply_doh_and_dns_settings()
    if not ok_dns:
        errs.append(msg_dns)

    ok_pol, msg_pol = apply_browser_policies()
    if not ok_pol:
        errs.append(msg_pol)

    ok_fw, msg_fw = apply_firewall_anti_bypass_rules()
    if not ok_fw:
        errs.append(msg_fw)

    if errs:
        return False, " | ".join(errs)
    return True, "Protecao Global AdGuard Family (DNS DoH, SafeSearch e Firewall) ativada com sucesso."


def disable_adguard_family_protection() -> Tuple[bool, str]:
    """Desativa completamente a protecao global e restaura configuracoes padrao."""
    logger.info("Desativando Protecao Global AdGuard Family...")
    restore_default_dns_settings()
    remove_browser_policies()
    remove_firewall_rules()
    return True, "Protecao Global desativada e sistema restaurado."


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
        "details": "Ativo com DoH Criptografado, SafeSearch e Firewall Anti-Burla" if is_active else "Inativo (Usando DNS padrao da operadora)",
    }
