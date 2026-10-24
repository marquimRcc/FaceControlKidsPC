<#
.SYNOPSIS
  Auditoria SOMENTE LEITURA de ACLs dos arquivos do FaceKids.
.DESCRIPTION
  Nao instala, desinstala, altera ACLs, cria tarefas, acessa biometria ou altera o login.
  Use em VM ou no PC do proprietario apenas para diagnostico voluntario.
#>
[CmdletBinding()]
param(
    [string]$Root = (Join-Path $env:ProgramData 'FaceKids')
)
$ErrorActionPreference = 'Stop'

$paths = @(
    $Root,
    (Join-Path $Root 'FaceKidsCredentialProvider.dll'),
    (Join-Path $Root 'iniciar-auth-service.bat'),
    (Join-Path $Root 'iniciar-filhos-agent.bat'),
    (Join-Path $Root 'auth_service.log'),
    (Join-Path $Root 'last_unlock.json'),
    (Join-Path $Root 'filhos_agent.log'),
    (Join-Path $Root 'criancas.sqlite3'),
    (Join-Path $Root 'criancas.sqlite3-wal'),
    (Join-Path $Root 'criancas.sqlite3-shm'),
    (Join-Path $Root 'fotos')
)
# Bits that permit data changes, deletion, ACL modification, or taking ownership.
# Read/execute flags are intentionally excluded; 'Modify' includes read flags.
$writeBits = 0x00000002 -bor 0x00000004 -bor 0x00000010 -bor 0x00000040 -bor
             0x00000100 -bor 0x00010000 -bor 0x00040000 -bor 0x00080000
# SID comparisons work independently of locale (BUILTIN\Users, Everyone etc).
# Include the actual child-account SID if the Windows account exists.
$broadSids = @('S-1-1-0', 'S-1-5-11', 'S-1-5-32-545')
$childAccount = Get-LocalUser -Name 'Filhos' -ErrorAction SilentlyContinue
if ($childAccount) { $broadSids += $childAccount.SID.Value }

$report = foreach ($path in $paths) {
    if (-not (Test-Path -LiteralPath $path)) {
        [pscustomobject]@{
            Path = $path; Exists = $false; Owner = $null
            BroadWriteAces = @(); Error = $null
        }
        continue
    }
    try {
        $acl = Get-Acl -LiteralPath $path -ErrorAction Stop
        $risky = @($acl.Access | Where-Object {
            $identity = $_.IdentityReference.Value
            $identitySid = try {
                $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
            } catch { $null }
            $isBroad = ($identitySid -in $broadSids) -or
                ($identity -match '(^|\\)(Filhos|Users|Usuarios|Usuários|Everyone|Todos|Authenticated Users|Usuários autenticados)
            $isAllow = $_.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Allow
            $canWrite = (([int]$_.FileSystemRights -band $writeBits) -ne 0)
            $isBroad -and $isAllow -and $canWrite
        } | ForEach-Object {
            [pscustomobject]@{
                Principal = $_.IdentityReference.Value
                Rights = $_.FileSystemRights.ToString()
                Inherited = $_.IsInherited
            }
        })
        [pscustomobject]@{
            Path = $path; Exists = $true; Owner = $acl.Owner
            BroadWriteAces = $risky; Error = $null
        }
    } catch {
        [pscustomobject]@{
            Path = $path; Exists = $true; Owner = $null
            BroadWriteAces = @(); Error = $_.Exception.GetType().Name
        }
    }
}

# Structured stdout only. No writes, no account passwords and no biometric data.
$report | ConvertTo-Json -Depth 5
)
            $isAllow = $_.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Allow
            $canWrite = (([int]$_.FileSystemRights -band $writeBits) -ne 0)
            $isBroad -and $isAllow -and $canWrite
        } | ForEach-Object {
            [pscustomobject]@{
                Principal = $_.IdentityReference.Value
                Rights = $_.FileSystemRights.ToString()
                Inherited = $_.IsInherited
            }
        })
        [pscustomobject]@{
            Path = $path; Exists = $true; Owner = $acl.Owner
            BroadWriteAces = $risky; Error = $null
        }
    } catch {
        [pscustomobject]@{
            Path = $path; Exists = $true; Owner = $null
            BroadWriteAces = @(); Error = $_.Exception.GetType().Name
        }
    }
}

# Structured stdout only. No writes, no account passwords and no biometric data.
$report | ConvertTo-Json -Depth 5
