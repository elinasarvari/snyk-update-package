# Run a Snyk open-source scan on every cloned repo in the list (repos/<name>/); keep the raw JSON per repo.
# PowerShell twin of snyk-scan.sh: same arguments, same outputs, same exit codes. Read-only for the repos.
# Works in Windows PowerShell 5.1 and PowerShell 7.
#
# Usage (from the project root):
#   powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-scan.ps1 <out-dir> [--workflow <id> | --manifest <file>] [extra snyk args...]
#   e.g. ... snyk-scan.ps1 workflows\wf-002-inventory-service\snyk --workflow 2 --org=my-org
#
# Which Snyk CLI is used, in this order:
#   1. $env:SNYK_CLI   - e.g. the CLI your Snyk VS Code extension downloaded (path in the extension's settings):
#                        $env:SNYK_CLI = "C:\Users\me\AppData\Local\snyk\snyk-win.exe"
#   2. `snyk` on PATH  - install: npm install -g snyk   (or scoop install snyk / the snyk-win.exe download)
#   3. common download folders of the Snyk VS Code extension / language server
# Log in once with the same SSO account as the extension:  & $env:SNYK_CLI auth   (or: snyk auth), or $env:SNYK_TOKEN.
#
# Outputs in <out-dir>:  <repo-name>.json, <repo-name>.err, scan-index.tsv (repo, path, exit, meaning)
# Then:  py -3 -I toolkit\scripts\parse-snyk.py <out-dir>\*.json --md findings.md --csv findings.csv
. (Join-Path $PSScriptRoot 'common.ps1')

if ($args.Count -lt 1) { Write-Err 'usage: snyk-scan.ps1 <out-dir> [--workflow <id> | --manifest <file>] [snyk args...]'; exit 64 }
$out = [string]$args[0]
$rest = @()
if ($args.Count -gt 1) { $rest = @($args[1..($args.Count - 1)] | ForEach-Object { [string]$_ }) }
$listArgs = @()
if ($rest.Count -ge 2 -and ($rest[0] -eq '--manifest' -or $rest[0] -eq '--workflow')) {
    $listArgs = @($rest[0], $rest[1])
    if ($rest.Count -gt 2) { $rest = @($rest[2..($rest.Count - 1)]) } else { $rest = @() }
}

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

$snyk = Find-SnykCli
if (-not $snyk) {
    Write-Err @'
Snyk CLI not found. Any one of these works:
  - Use the CLI your Snyk VS Code extension already downloaded (its path is in the extension's settings):
      $env:SNYK_CLI = "C:\path\to\snyk-win.exe"          (macOS/Linux: export SNYK_CLI=/path/to/snyk)
  - Install it:   npm install -g snyk     (macOS: brew tap snyk/tap && brew install snyk-cli)
Then log in once with the same SSO account:  & $env:SNYK_CLI auth   (or: snyk auth)
Or export `snyk test --all-projects --json` from CI and pass the file to parse-snyk.py instead.
'@
    exit 127
}
Write-Err "Using Snyk CLI: $snyk"
# `whoami` works for both kinds of login: a token (snyk config / SNYK_TOKEN) and browser/SSO (OAuth).
$devNull = if ($OnWindows) { 'NUL' } else { '/dev/null' }
if (-not $env:SNYK_TOKEN) {
    $loggedIn = Invoke-ShellCommand -Cwd (Get-Location).Path -CommandLine ((Format-Arg $snyk) + ' whoami --experimental') `
        -Stdout $devNull -Stderr $devNull
    if ($loggedIn -ne 0) {
        Write-Err "Snyk is not logged in - run: & `"$snyk`" auth   (opens your browser for SSO), or set `$env:SNYK_TOKEN."
        exit 126
    }
}

New-Item -ItemType Directory -Force -Path $out | Out-Null
$out = Get-FullPath $out
$index = Join-Path $out 'scan-index.tsv'
Write-Utf8File $index "repo`tpath`texit`tmeaning`n"

$repos = @(Invoke-Python (@((Join-Path $PSScriptRoot 'repos.py')) + $listArgs + @('list')))
if ($LASTEXITCODE -ne 0) { $repos | ForEach-Object { Write-Err $_ }; exit 2 }
$extra = ($rest | ForEach-Object { Format-Arg $_ }) -join ' '

foreach ($row in $repos) {
    if (-not $row) { continue }
    $cols = $row -split "`t"
    $name = $cols[0]; $dir = $cols[1]
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) {
        Add-Utf8Line $index "$name`t$dir`t-`tnot cloned - run repos.py clone $name"
        Write-Err "SKIP ${name}: $dir does not exist (not cloned yet?)"
        continue
    }
    Write-Err "SCAN $name ($dir)"
    # --all-projects picks up every pom/gradle file under the path (multi-module included).
    $code = Invoke-ShellCommand -Cwd $dir -CommandLine ((Format-Arg $snyk) + " test --all-projects --json $extra").TrimEnd() `
        -Stdout (Join-Path $out "$name.json") -Stderr (Join-Path $out "$name.err")
    $meaning = switch ($code) {
        0 { 'no vulnerabilities' } 1 { 'vulnerabilities found' } 2 { "scan failed - see $name.err" }
        3 { 'no supported project found' } default { 'unexpected exit' }
    }
    Add-Utf8Line $index "$name`t$dir`t$code`t$meaning"
}

Get-Content -LiteralPath $index | ForEach-Object { Write-Err ($_ -replace "`t", '  ') }
exit 0
