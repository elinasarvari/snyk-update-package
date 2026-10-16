# Collect the dependency facts the inventory/analysis phases need from one Maven repo.
# PowerShell twin of maven-facts.sh: same arguments, same outputs. Read-only for the repo (writes only <out-dir>).
# Works in Windows PowerShell 5.1 and PowerShell 7.
#
# Usage: maven-facts.ps1 <repo-dir> <out-dir> [artifact-filter ...]
#   e.g. powershell -ExecutionPolicy Bypass -File toolkit\scripts\maven-facts.ps1 repos\inventory-service\backend out spring-boot camel
#
# Outputs in <out-dir>: facts.env, dependency-tree.txt, filtered-tree.txt, declared.txt, version-props.txt
. (Join-Path $PSScriptRoot 'common.ps1')

if ($args.Count -lt 2) { Write-Err 'usage: maven-facts.ps1 <repo-dir> <out-dir> [artifact-filter ...]'; exit 64 }
$repoArg = [string]$args[0]
$out = [string]$args[1]
$filters = @()
if ($args.Count -gt 2) { $filters = @($args[2..($args.Count - 1)] | ForEach-Object { [string]$_ }) }

New-Item -ItemType Directory -Force -Path $out | Out-Null
$out = Get-FullPath $out
if (-not (Test-Path -LiteralPath $repoArg -PathType Container)) { Write-Err "cannot cd to $repoArg"; exit 2 }
$repo = Get-FullPath $repoArg
Set-Location -LiteralPath $repo
$factsFile = Join-Path $out 'facts.env'

if (-not (Test-Path 'pom.xml')) {
    Write-Utf8File $factsFile "BUILD_TOOL=unsupported`n"
    Write-Err "No pom.xml in $repo - this script only handles Maven. Gradle: run 'gradlew dependencies'."
    exit 3
}

if ($OnWindows -and (Test-Path 'mvnw.cmd')) { $mvn = 'mvnw.cmd' }
elseif (-not $OnWindows -and (Test-Executable './mvnw')) { $mvn = './mvnw' }
else { $mvn = 'mvn' }

function Get-PomValue([string]$Expression) {
    $tmp = Join-Path $out ('.eval-' + [guid]::NewGuid().ToString('N') + '.txt')
    $null = Invoke-ShellCommand -Cwd $repo -CommandLine "$mvn -q -N help:evaluate -Dexpression=$Expression -DforceStdout" `
        -Stdout $tmp -Stderr ($(if ($OnWindows) { 'NUL' } else { '/dev/null' }))
    $value = ''
    if (Test-Path -LiteralPath $tmp) { $value = ([System.IO.File]::ReadAllText($tmp)).Trim(); Remove-Item -LiteralPath $tmp -Force }
    return $value
}

$envInfo = (Invoke-Helper @('env-info')) -join '' | ConvertFrom-Json
$dirty = @(& git status --porcelain 2>$null | Where-Object { $_ }).Count
$facts = @(
    "BUILD_TOOL=maven ($mvn)",
    ('PARENT={0}:{1}:{2}' -f (Get-PomValue 'project.parent.groupId'), (Get-PomValue 'project.parent.artifactId'), (Get-PomValue 'project.parent.version')),
    ('PROJECT_JAVA=' + ((Invoke-Helper @('project-java', 'pom.xml')) -join '')),
    ('JVM=' + $envInfo.java),
    ('GIT_BRANCH=' + $envInfo.branch),
    ('GIT_COMMIT=' + $envInfo.commit),
    "GIT_DIRTY=$dirty files")
Write-Utf8File $factsFile (($facts -join "`n") + "`n")

# appendOutput keeps every module's tree in a multi-module build.
$tree = Join-Path $out 'dependency-tree.txt'
Remove-Item -LiteralPath $tree -Force -ErrorAction SilentlyContinue
$treeLog = Join-Path $out 'dependency-tree.log'
$code = Invoke-ShellCommand -Cwd $repo -CommandLine "$mvn -q dependency:tree `"-DoutputFile=$tree`" -DappendOutput=true" `
    -Stdout $treeLog -Stderr $treeLog
if ($code -ne 0) { Write-Err "dependency:tree failed - see $treeLog" }

$filtered = Join-Path $out 'filtered-tree.txt'
Write-Utf8File $filtered ''
if ($filters.Count -gt 0 -and (Test-Path -LiteralPath $tree)) {
    Invoke-Helper (@('filter-tree', $tree, $filtered) + $filters) | Out-Null
}

$declared = Join-Path $out 'declared.txt'
$props = Join-Path $out 'version-props.txt'
Write-Utf8File $declared ''
Write-Utf8File $props ''
# skips target/, node_modules/, .git/ ... (toolkit/ignore-dirs.txt)
$poms = @(Invoke-Helper @('find-poms') | Where-Object { $_ })
foreach ($pom in $poms) {
    foreach ($line in @(Invoke-Helper @('pom-declared', $pom) 2>$null)) { Add-Utf8Line $declared $line }
    foreach ($line in @(Invoke-Helper @('version-props', $pom) 2>$null)) { Add-Utf8Line $props $line }
}

Get-Content -LiteralPath $factsFile
$treeLines = 0
if (Test-Path -LiteralPath $tree) { $treeLines = @(Get-Content -LiteralPath $tree).Count }
'declared deps: {0}  tree lines: {1}' -f @(Get-Content -LiteralPath $declared).Count, $treeLines
