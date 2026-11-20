$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'

function Find-UsablePython([string]$Candidate) {
    try {
        $result = & $Candidate -c 'import sys, tkinter; assert sys.version_info >= (3,9); print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) {
            return [string]($result | Select-Object -Last 1)
        }
    } catch { }
    return $null
}

# Honor an explicit interpreter before inspecting unrelated installations.
if ($env:IMAGE_MASK_PYTHON) {
    $python = Find-UsablePython $env:IMAGE_MASK_PYTHON
    if ($python) {
        & $python (Join-Path $PSScriptRoot 'launcher.py')
        exit $LASTEXITCODE
    }
}

$candidates = [System.Collections.Generic.List[string]]::new()
foreach ($name in @('python', 'python3', 'py')) {
    try {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue
        if ($command) {
            $candidates.Add($command.Source)
            if ($name -eq 'py') {
                try {
                    & $command.Source -0p 2>$null | ForEach-Object {
                        if ("$_" -match '([A-Za-z]:\\.*python(?:w)?\.exe)\s*$') { $candidates.Add($Matches[1]) }
                    }
                } catch { }
            }
        }
    } catch { }
}
foreach ($registry in @('HKCU:\Software\Python', 'HKLM:\Software\Python', 'HKLM:\Software\WOW6432Node\Python')) {
    try {
        if (Test-Path $registry) {
            Get-ChildItem $registry -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -eq 'InstallPath' } | ForEach-Object {
                try {
                    $exe = $_.GetValue('ExecutablePath')
                    if (-not $exe -and $_.GetValue('')) { $exe = Join-Path $_.GetValue('') 'python.exe' }
                    if ($exe) { $candidates.Add($exe) }
                } catch { }
            }
        }
    } catch { }
}
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    $python = Find-UsablePython $candidate
    if ($python) {
        & $python (Join-Path $PSScriptRoot 'launcher.py')
        exit $LASTEXITCODE
    }
}
Write-Host 'No usable Python found. Python 3.9+ with tkinter is required.'
Write-Host 'Run: your-python.exe launcher.py'
Write-Host 'Or set IMAGE_MASK_PYTHON to your Python executable path.'
exit 1
