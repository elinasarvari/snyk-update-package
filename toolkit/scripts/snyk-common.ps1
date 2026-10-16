# Shared by snyk-scan.ps1 and snyk-login.ps1 (dot-source it after common.ps1). Bash twin: snyk-common.sh.
#   Find-SnykCli        -> path of the Snyk CLI to use ($env:SNYK_CLI, `snyk` on PATH, the VS Code extension's download)
#   Show-CliMissingHelp -> how to get one (stderr)
#   Test-SnykLogin      -> $true only if Snyk itself accepts the login (`snyk whoami` with the stored OAuth token,
#                          or SNYK_TOKEN / SNYK_OAUTH_TOKEN from the environment). Never assumed.
#   Get-SnykUser        -> the logged-in username, if any

function Find-SnykCli {
    if ($env:SNYK_CLI) {
        if (Test-Executable $env:SNYK_CLI) { return $env:SNYK_CLI }
        Write-Err "SNYK_CLI is set to '$($env:SNYK_CLI)', but that is not an executable file."
        return $null
    }
    $onPath = Get-Command snyk -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($onPath) { return $onPath.Source }
    # Where the Snyk VS Code extension / language server usually downloads its CLI. Locations vary by version
    # and OS - if yours is elsewhere, set SNYK_CLI (the path is in the extension's settings).
    $patterns = @()
    if ($OnWindows) {
        foreach ($root in @($env:LOCALAPPDATA, $env:APPDATA)) {
            if ($root) {
                $patterns += (Join-Path $root 'snyk\snyk-win*')
                $patterns += (Join-Path $root 'Code\User\globalStorage\snyk-security.snyk-vulnerability-scanner\snyk*')
            }
        }
    } else {
        $patterns += "$HOME/Library/Application Support/snyk/snyk-macos*"
        $patterns += "$HOME/Library/Application Support/Code/User/globalStorage/snyk-security.snyk-vulnerability-scanner/snyk*"
        $patterns += "$HOME/.local/share/snyk/snyk-linux*"
        $patterns += "$HOME/.config/Code/User/globalStorage/snyk-security.snyk-vulnerability-scanner/snyk*"
    }
    foreach ($pattern in $patterns) {
        foreach ($candidate in @(Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue)) {
            if (Test-Executable $candidate.FullName) { return $candidate.FullName }
        }
    }
    return $null
}

function Show-CliMissingHelp {
    Write-Err @'
Snyk CLI not found. Any one of these works:
  - Use the CLI your Snyk VS Code extension already downloaded (its path is in the extension's settings):
      $env:SNYK_CLI = "C:\path\to\snyk-win.exe"          (macOS/Linux: export SNYK_CLI=/path/to/snyk)
  - Install it:   npm install -g snyk     (macOS: brew tap snyk/tap && brew install snyk-cli)
Then log in once with the same SSO account:  powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-login.ps1
Or export `snyk test --all-projects --json` from CI and pass the file to parse-snyk.py instead.
'@
}

function Get-SnykUser {
    $out = @(& $script:SnykCli whoami --experimental 2>$null)
    if ($LASTEXITCODE -ne 0) { return '' }
    return ([string]($out | Where-Object { $_ } | Select-Object -Last 1)).Trim()
}

function Test-SnykLogin {
    # Always ask Snyk - also when a token is set in the environment (it could be expired or for another region).
    $null = @(& $script:SnykCli whoami --experimental 2>$null)
    return ($LASTEXITCODE -eq 0)
}
