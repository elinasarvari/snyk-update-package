# Run the whole test suite from PowerShell (Windows PowerShell 5.1 or PowerShell 7, any OS).
# Safe: throwaway sandboxes only, never your real repos or GitHub.
#   powershell -ExecutionPolicy Bypass -File tests\run.ps1            # fast suite
#   $env:RUN_MAVEN_TESTS = "1"; powershell -ExecutionPolicy Bypass -File tests\run.ps1   # + a real Maven build
# Which PowerShell the .ps1 tests use: $env:SUP_PS (e.g. "powershell" for 5.1), else pwsh, else powershell.
. (Join-Path (Join-Path $PSScriptRoot '..') 'toolkit/scripts/common.ps1')
Set-Location -LiteralPath (Get-FullPath (Join-Path $PSScriptRoot '..'))
$py = Get-Python
$prefix = @()
if ($py.Count -gt 1) { $prefix = $py[1..($py.Count - 1)] }
# (assign arrays directly: an `if` that yields a 1-item array hands back the bare item)
$extra = @('-v')
if ($args.Count -gt 0) { $extra = @($args) }
& $py[0] @prefix '-I' '-m' 'unittest' 'discover' '-s' 'tests' '-p' 'test_*.py' @extra
exit $LASTEXITCODE
