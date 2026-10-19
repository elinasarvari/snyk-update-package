# Build, test and (optionally) boot one repository, writing a machine-readable summary.
# PowerShell twin of verify-repo.sh: same arguments, same outputs, same exit codes. Parsing lives in script-helpers.py.
# Works in Windows PowerShell 5.1 and PowerShell 7.
#
# Usage: verify-repo.ps1 <repo-dir> <out-dir> [--smoke] [--build-cmd "<cmd>"]
#   e.g. powershell -ExecutionPolicy Bypass -File toolkit\scripts\verify-repo.ps1 repos\inventory-service\backend out --smoke
#   --smoke       (Spring Boot apps only) after a green build, start the packaged jar on a random port and wait for
#                 Spring Boot's "Started ... in" line
#   --build-cmd   override the auto-detected build command (Windows: mvnw.cmd / mvn / gradlew.bat / gradle)
#
# Outputs in <out-dir>: build.log, smoke.log, summary.json - nothing is written into the repo itself.
# The smoke boot runs with <out-dir> as its working folder. Files the build leaves in the repo that git doesn't
# ignore are reported as "left_in_repo" (never deleted).
# Exit code: 0 all green, 1 build/tests failed, 2 smoke failed, 3 unsupported repo
# (like verify-repo.sh: a missing <repo-dir>/<out-dir> exits 1, an unknown argument exits 64)
. (Join-Path $PSScriptRoot 'common.ps1')

if ($args.Count -lt 1) { Write-Err 'repo dir required'; exit 1 }
if ($args.Count -lt 2) { Write-Err 'out dir required'; exit 1 }
$repoArg = [string]$args[0]
$out = [string]$args[1]
$smoke = $false
$buildCmd = ''
$i = 2
while ($i -lt $args.Count) {
    switch ([string]$args[$i]) {
        '--smoke' { $smoke = $true }
        '--build-cmd' { $i++; $buildCmd = [string]$args[$i] }
        default { Write-Err "unknown arg $($args[$i])"; exit 64 }
    }
    $i++
}

New-Item -ItemType Directory -Force -Path $out | Out-Null
$out = Get-FullPath $out
if (-not (Test-Path -LiteralPath $repoArg -PathType Container)) { Write-Err "cannot cd to $repoArg"; exit 3 }
$repo = Get-FullPath $repoArg
Set-Location -LiteralPath $repo

if (-not $buildCmd) {
    if (Test-Path 'pom.xml') {
        if ($OnWindows -and (Test-Path 'mvnw.cmd')) { $buildCmd = 'mvnw.cmd -B clean verify' }
        elseif (-not $OnWindows -and (Test-Executable './mvnw')) { $buildCmd = './mvnw -B clean verify' }
        else { $buildCmd = 'mvn -B clean verify' }
    } elseif (Get-ChildItem -Filter 'build.gradle*' -ErrorAction SilentlyContinue) {
        if ($OnWindows -and (Test-Path 'gradlew.bat')) { $buildCmd = 'gradlew.bat clean build' }
        elseif (-not $OnWindows -and (Test-Executable './gradlew')) { $buildCmd = './gradlew clean build' }
        else { $buildCmd = 'gradle clean build' }
    } else {
        Invoke-Helper @('summary', (Join-Path $out 'summary.json'), "repo=$repo", 'status=unsupported') | Out-Null
        Write-Err "No pom.xml or build.gradle in $repo"
        exit 3
    }
}

$snapshot = Join-Path $out '.before-build.json'
Invoke-Helper @('git-snapshot', $snapshot) | Out-Null

$buildLog = Join-Path $out 'build.log'
$started = Get-Date
$buildExit = Invoke-ShellCommand -Cwd $repo -CommandLine $buildCmd -Stdout $buildLog -Stderr $buildLog
$duration = [int]((Get-Date) - $started).TotalSeconds

# every module's JUnit reports (multi-module builds included)
$testsJson = (Invoke-Helper @('junit')) -join ''

$smokeStatus = 'skipped'
if ($smoke -and $buildExit -eq 0) {
    $jar = @(Get-ChildItem -Path 'target', (Join-Path 'build' 'libs') -Filter '*.jar' -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch '-(plain|sources|javadoc|tests)\.jar$' } | Sort-Object FullName | Select-Object -First 1)
    if ($jar.Count -eq 0) {
        $smokeStatus = 'no-jar'
    } else {
        $smokeLog = Join-Path $out 'smoke.log'
        $smokeErr = Join-Path $out 'smoke.err'
        $java = Get-Command java -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $java) {
            Write-Utf8File $smokeLog 'java not found on PATH'
            $smokeStatus = 'failed'
        } else {
            $proc = Start-Process -FilePath $java.Source -ArgumentList @('-jar', ('"' + $jar[0].FullName + '"'), '--server.port=0') `
                -WorkingDirectory $out -RedirectStandardOutput $smokeLog -RedirectStandardError $smokeErr -NoNewWindow -PassThru
            $smokeStatus = 'timeout'
            for ($n = 0; $n -lt 90; $n++) {
                Start-Sleep -Seconds 1
                $text = ''
                foreach ($f in @($smokeLog, $smokeErr)) {
                    if (Test-Path -LiteralPath $f) { $text += [System.IO.File]::ReadAllText($f) }
                }
                if ($text -match 'Started [A-Za-z0-9_$]+ in') { $smokeStatus = 'started'; break }
                if ($text -match 'APPLICATION FAILED TO START' -or $proc.HasExited) { $smokeStatus = 'failed'; break }
            }
            if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
            $proc.WaitForExit(10000) | Out-Null
            if (Test-Path -LiteralPath $smokeErr) {
                [System.IO.File]::AppendAllText($smokeLog, [System.IO.File]::ReadAllText($smokeErr), $Utf8NoBom)
                Remove-Item -LiteralPath $smokeErr -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

$leftInRepo = (Invoke-Helper @('left-in-repo', $snapshot)) -join ''
Remove-Item -LiteralPath $snapshot -Force -ErrorAction SilentlyContinue

$status = 'green'
$exitCode = 0
if ($buildExit -ne 0) { $status = 'build-failed'; $exitCode = 1 }
elseif (@('failed', 'timeout', 'no-jar') -contains $smokeStatus) { $status = 'smoke-failed'; $exitCode = 2 }

# Fields go through a file: Windows PowerShell 5.1 drops quotes inside arguments to native programs.
$fields = Join-Path $out '.summary-fields.txt'
Write-Utf8File $fields ((@(
    "repo=$repo", "build_cmd=$buildCmd", "build_exit:=$buildExit", "duration_s:=$duration", "tests:=$testsJson",
    "smoke=$smokeStatus", "left_in_repo:=$leftInRepo", "status=$status") -join "`n") + "`n")
Invoke-Helper @('summary', (Join-Path $out 'summary.json'), '--env', '--fields', $fields)
Remove-Item -LiteralPath $fields -Force -ErrorAction SilentlyContinue

if ($leftInRepo -ne '[]') { Write-Output "--- WARNING: the build left files in the repo that git doesn't ignore: $leftInRepo" }
if ($buildExit -ne 0) {
    Write-Output '--- first errors from build.log ---'
    Invoke-Helper @('first-errors', $buildLog, '40')
}
exit $exitCode
