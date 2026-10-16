# Log the Snyk CLI in with OAuth2 - no clicking around in the VS Code extension.
# PowerShell twin of snyk-login.sh: same options, same exit codes. Works in Windows PowerShell 5.1 and PowerShell 7.
#
# Usage: powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-login.ps1
#          [--status | --logout | --force] [--browser | --client-credentials] [--endpoint <url>]
#   (no option)            already logged in? say who. Otherwise log in:
#                            - $env:SNYK_CLIENT_ID + $env:SNYK_CLIENT_SECRET set -> OAuth2 client credentials
#                              (service account, no browser; Snyk Enterprise)
#                            - otherwise -> OAuth2 in your browser: it opens by itself, sign in with your company SSO.
#                              The CLI keeps a token that renews itself, so this is a one-time step.
#   --status               only report: exit 0 if logged in, 126 if not
#   --force                log in again even if already logged in
#   --browser              always use the browser login, even if client credentials are set
#   --client-credentials   always use client credentials (fails if SNYK_CLIENT_ID / SNYK_CLIENT_SECRET aren't set)
#   --endpoint <url>       first point the CLI at your Snyk region / private instance (saved in the CLI config),
#                          e.g. --endpoint https://api.eu.snyk.io   (check the URL with your Snyk admin)
#   --logout               log the CLI out
#
# The client secret is read from the environment only, and never printed or written to a file
# (the CLI is called directly, not through a temporary script).
# Exit codes: 0 logged in (or logged out with --logout), 126 not logged in, 127 no Snyk CLI, 64 bad arguments
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot 'snyk-common.ps1')

$mode = 'login'; $force = $false; $method = 'auto'; $endpoint = ''
$i = 0
while ($i -lt $args.Count) {
    switch ([string]$args[$i]) {
        '--status' { $mode = 'status' }
        '--logout' { $mode = 'logout' }
        '--force' { $force = $true }
        '--browser' { $method = 'browser' }
        '--client-credentials' { $method = 'client' }
        '--endpoint' {
            $i++
            if ($i -ge $args.Count) { Write-Err '--endpoint needs a URL'; exit 64 }
            $endpoint = [string]$args[$i]
        }
        default { Write-Err "unknown option $($args[$i]) (see the top of snyk-login.ps1)"; exit 64 }
    }
    $i++
}

$script:SnykCli = Find-SnykCli
if (-not $script:SnykCli) { Show-CliMissingHelp; exit 127 }
$snyk = $script:SnykCli
Write-Output "Using Snyk CLI: $snyk"

if ($endpoint) {
    $null = & $snyk config set "endpoint=$endpoint" 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Err 'could not set the endpoint'; exit 64 }
    Write-Output "Snyk endpoint set to $endpoint"
}

if ($mode -eq 'status') {
    if (Test-SnykLogin) { Write-Output "Logged in to Snyk as $(Get-SnykUser)"; exit 0 }
    Write-Output 'Not logged in to Snyk - run: powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-login.ps1'
    exit 126
}
if ($mode -eq 'logout') {
    $null = & $snyk logout 2>$null
    Write-Output 'Logged out of Snyk'
    exit 0
}

if (-not $force -and (Test-SnykLogin)) {
    Write-Output "Already logged in to Snyk as $(Get-SnykUser) - nothing to do"
    exit 0
}
if ($env:SNYK_TOKEN -or $env:SNYK_OAUTH_TOKEN) {
    Write-Output 'Note: SNYK_TOKEN / SNYK_OAUTH_TOKEN is set in this shell, Snyk rejects it, and the CLI uses it instead of a login. Unset it, or replace it.'
}

if ($method -eq 'auto') {
    $method = 'browser'
    if ($env:SNYK_CLIENT_ID -and $env:SNYK_CLIENT_SECRET) { $method = 'client' }
}

if ($method -eq 'client') {
    if (-not ($env:SNYK_CLIENT_ID -and $env:SNYK_CLIENT_SECRET)) {
        Write-Err '--client-credentials needs SNYK_CLIENT_ID and SNYK_CLIENT_SECRET (a Snyk service account)'
        exit 64
    }
    Write-Output "Logging in with OAuth2 client credentials (service account $($env:SNYK_CLIENT_ID)) ..."
    $null = & $snyk auth '--auth-type=oauth' "--client-id=$($env:SNYK_CLIENT_ID)" "--client-secret=$($env:SNYK_CLIENT_SECRET)" 2>$null
} else {
    Write-Output 'Opening your browser for the Snyk login (OAuth2). Sign in with your company SSO, then come back here.'
    Write-Output 'If no browser opens, copy the link the Snyk CLI prints below into your browser.'
    & $snyk auth '--auth-type=oauth'
}

if (Test-SnykLogin) {
    Write-Output "Logged in to Snyk as $(Get-SnykUser)"
    exit 0
}
Write-Err 'Snyk login did not complete. Try again, or check with your Snyk admin that SSO login is enabled for you.'
exit 126
