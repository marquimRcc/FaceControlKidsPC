<#
.SYNOPSIS
  Smoke test dinamico de seguranca do servidor HTTP local do SafePCKids.
.DESCRIPTION
  Executa probes negativos somente contra 127.0.0.1 para validar que:
  - Path traversal em /assets/ e /ui/ retorna 403
  - Origem CORS externa em rota administrativa retorna 403
  - Token de sessao invalido retorna 401
  Nao altera banco, servicos ou configuracoes.
#>
[CmdletBinding()]
param(
    [int]$Port = 8765
)
$ErrorActionPreference = 'Stop'
$base = "http://127.0.0.1:$Port"

function Invoke-Probe {
    param(
        [string]$Method,
        [string]$Path,
        [hashtable]$Headers = @{},
        [string]$Body = $null
    )
    try {
        $params = @{
            Uri = "$base$Path"
            Method = $Method
            Headers = $Headers
            TimeoutSec = 5
            UseBasicParsing = $true
        }
        if ($null -ne $Body) {
            $params.Body = $Body
            $params.ContentType = 'application/json'
        }
        $resp = Invoke-WebRequest @params
        return [int]$resp.StatusCode
    } catch {
        $webResp = $_.Exception.Response
        if ($webResp) {
            return [int]$webResp.StatusCode
        }
        throw
    }
}

$hb = Invoke-Probe -Method 'GET' -Path '/api/heartbeat'
if ($hb -ne 200) { throw "Servidor nao respondeu /api/heartbeat em $base (status $hb)" }

$tests = @(
    @{ Name = 'Path traversal /assets'; Method = 'GET'; Path = '/assets/../../pyproject.toml'; Headers = @{}; Expected = 403 },
    @{ Name = 'Path traversal /ui'; Method = 'GET'; Path = '/ui/../../pyproject.toml'; Headers = @{}; Expected = 403 },
    @{ Name = 'CORS externo em /api/dashboard'; Method = 'GET'; Path = '/api/dashboard'; Headers = @{ Origin = 'https://evil.example' }; Expected = 403 },
    @{ Name = 'Token invalido em /api/dashboard'; Method = 'GET'; Path = '/api/dashboard'; Headers = @{ 'X-Session-Token' = 'token-invalido' }; Expected = 401 }
)

foreach ($t in $tests) {
    $code = Invoke-Probe -Method $t.Method -Path $t.Path -Headers $t.Headers
    if ($code -ne $t.Expected) {
        throw "FALHA [$($t.Name)]: esperado HTTP $($t.Expected), obtido $code"
    }
    Write-Host "PASS [$($t.Name)] -> HTTP $code" -ForegroundColor Green
}

Write-Host 'Todos os probes de seguranca HTTP passaram.' -ForegroundColor Cyan
