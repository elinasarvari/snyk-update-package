# Shared by the PowerShell twins of the toolkit scripts (snyk-scan.ps1, verify-repo.ps1, maven-facts.ps1).
# Works in Windows PowerShell 5.1 and PowerShell 7 (Windows, macOS, Linux). Dot-source it:  . "$PSScriptRoot\common.ps1"
#
# Two PowerShell 5.1 traps are avoided on purpose:
#   - `> file` writes UTF-16 and re-encodes native output -> commands with redirected output run inside a small
#     temporary .cmd (Windows) or .sh (elsewhere) script, so the OS shell writes the bytes unchanged;
#   - quotes inside arguments to native programs are dropped -> anything with quotes goes through files.

Set-StrictMode -Version 2
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONUTF8 = '1'

$script:OnWindows = ($env:OS -eq 'Windows_NT')
$script:Utf8NoBom = New-Object System.Text.UTF8Encoding $false
$script:Helpers = Join-Path $PSScriptRoot 'script-helpers.py'

function Write-Utf8File([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text, $script:Utf8NoBom)
}

function Add-Utf8Line([string]$Path, [string]$Line) {
    [System.IO.File]::AppendAllText($Path, $Line + "`n", $script:Utf8NoBom)
}

function Write-Err([string]$Message) { [Console]::Error.WriteLine($Message) }

function Get-FullPath([string]$Path) {
    if (-not [System.IO.Path]::IsPathRooted($Path)) { $Path = Join-Path (Get-Location).Path $Path }
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
}

function Get-Python {
    # Returns @(exe, prefix-args...). On Windows prefer the `py` launcher: `python3` there is often the Store stub.
    $names = @('python3', 'python')
    if ($script:OnWindows) { $names = @('py', 'python', 'python3') }
    foreach ($name in $names) {
        $cmd = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) {
            if ($name -eq 'py') { return ,@($cmd.Source, '-3') }
            return ,@($cmd.Source)       # leading comma: keep a 1-item array an array
        }
    }
    throw 'Python 3 not found. Install it from python.org (Windows: tick "Add python.exe to PATH") and try again.'
}

function Invoke-Python {
    # Runs python -I <args>; returns its stdout lines. No argument may contain double quotes (PowerShell 5.1).
    param([string[]]$PyArgs)
    $py = Get-Python
    $prefix = @()
    if ($py.Count -gt 1) { $prefix = $py[1..($py.Count - 1)] }
    & $py[0] @prefix '-I' @PyArgs
}

function Invoke-Helper { param([string[]]$HelperArgs) Invoke-Python (@($script:Helpers) + $HelperArgs) }

function Format-Arg([string]$Value) {
    # Quote one argument for the temporary cmd/sh script.
    if ($Value -match '^[A-Za-z0-9_./:=@%+,\\-]+$') { return $Value }
    if ($script:OnWindows) { return '"' + $Value.Replace('"', '""') + '"' }
    return "'" + $Value.Replace("'", "'\''") + "'"
}

function Invoke-ShellCommand {
    # Runs one command line in the OS shell (cmd.exe on Windows, bash elsewhere) inside $Cwd.
    # -Stdout/-Stderr: files to write to (the same file twice merges them). Returns the exit code.
    param([string]$Cwd, [string]$CommandLine, [string]$Stdout, [string]$Stderr)
    $tmp = [System.IO.Path]::GetTempPath()
    $id = [guid]::NewGuid().ToString('N')
    if ($script:OnWindows) {
        $script = Join-Path $tmp "sup-$id.cmd"
        $redir = ''
        if ($Stdout) { $redir += " > `"$Stdout`"" }
        if ($Stderr -and $Stderr -eq $Stdout) { $redir += ' 2>&1' } elseif ($Stderr) { $redir += " 2> `"$Stderr`"" }
        $body = "@echo off`r`nchcp 65001 >nul`r`ncd /d `"$Cwd`"`r`n$CommandLine$redir`r`nexit /b %ERRORLEVEL%`r`n"
        Write-Utf8File $script $body
        & cmd.exe /d /c $script | Out-Host
    } else {
        $script = Join-Path $tmp "sup-$id.sh"
        $redir = ''
        if ($Stdout) { $redir += " > '$Stdout'" }
        if ($Stderr -and $Stderr -eq $Stdout) { $redir += ' 2>&1' } elseif ($Stderr) { $redir += " 2> '$Stderr'" }
        Write-Utf8File $script "cd '$Cwd' || exit 125`n$CommandLine$redir`n"
        & bash $script | Out-Host
    }
    $code = $LASTEXITCODE
    Remove-Item -LiteralPath $script -Force -ErrorAction SilentlyContinue
    return $code
}

function Test-Executable([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    if ($script:OnWindows) { return $true }
    & test -x $Path
    return ($LASTEXITCODE -eq 0)
}
