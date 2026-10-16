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
# Log in once with the same SSO account as the extension:  ...\snyk-login.ps1  (OAuth2, opens your browser).
#
# Never scans inside the folders in toolkit\ignore-dirs.txt (target\, node_modules\, ...): they are passed to
# Snyk as --exclude=..., merged with any --exclude=... you give.
#
# Outputs in <out-dir>:  <repo-name>.json, <repo-name>.err, scan-index.tsv (repo, path, exit, meaning)
# Then:  py -3 -I toolkit\scripts\parse-snyk.py <out-dir>\*.json --md findings.md --csv findings.csv
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot 'snyk-common.ps1')

if ($args.Count -lt 1) { Write-Err 'usage: snyk-scan.ps1 <out-dir> [--workflow <id> | --manifest <file>] [snyk args...]'; exit 64 }
$out = [string]$args[0]
$rest = @()
if ($args.Count -gt 1) { $rest = @($args[1..($args.Count - 1)] | ForEach-Object { [string]$_ }) }
$listArgs = @()
if ($rest.Count -ge 2 -and ($rest[0] -eq '--manifest' -or $rest[0] -eq '--workflow')) {
    $listArgs = @($rest[0], $rest[1])
    if ($rest.Count -gt 2) { $rest = @($rest[2..($rest.Count - 1)]) } else { $rest = @() }
}


$script:SnykCli = Find-SnykCli
$snyk = $script:SnykCli
if (-not $snyk) { Show-CliMissingHelp; exit 127 }
Write-Err "Using Snyk CLI: $snyk"
# Works for every kind of login: browser/SSO (OAuth), service-account client credentials, API token.
if (-not (Test-SnykLogin)) {
    Write-Err 'Snyk is not logged in - run: powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-login.ps1   (opens your browser for SSO)'
    exit 126
}

New-Item -ItemType Directory -Force -Path $out | Out-Null
$out = Get-FullPath $out
$index = Join-Path $out 'scan-index.tsv'
Write-Utf8File $index "repo`tpath`texit`tmeaning`n"

$repos = @(Invoke-Python (@((Join-Path $PSScriptRoot 'repos.py')) + $listArgs + @('list')))
if ($LASTEXITCODE -ne 0) { $repos | ForEach-Object { Write-Err $_ }; exit 2 }
# Build output and dependency folders are never scanned: merge them into one --exclude=...
$exclude = (Invoke-Helper @('ignore-dirs', '--comma')) -join ''
$snykArgs = @()
foreach ($arg in $rest) {
    if ($arg -like '--exclude=*') { $exclude = $arg.Substring(10) + ',' + $exclude } else { $snykArgs += $arg }
}
$snykArgs += "--exclude=$exclude"
$extra = ($snykArgs | ForEach-Object { Format-Arg $_ }) -join ' '

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
