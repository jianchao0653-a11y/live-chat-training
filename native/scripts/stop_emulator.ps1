$ErrorActionPreference = 'Stop'
$lensRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$lensRecordPath = Join-Path $lensRoot 'output/native/emulator-process.json'
if (-not (Test-Path -LiteralPath $lensRecordPath)) { return }
$lensRecord = Get-Content -LiteralPath $lensRecordPath -Raw | ConvertFrom-Json
if ($lensRecord.status -eq 'stopped') { return }
$lensProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($lensRecord.pid)"
if ($lensProcess) {
    if ($lensProcess.CommandLine -notmatch 'LensPreview' -or $lensProcess.Name -ne 'emulator.exe') {
        throw 'Process identity mismatch; no process was stopped.'
    }
    $lensChildren = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($lensRecord.pid)"
    foreach ($lensChild in $lensChildren) { Stop-Process -Id $lensChild.ProcessId -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $lensRecord.pid -Force -ErrorAction SilentlyContinue
}
$lensRecord | Add-Member -NotePropertyName status -NotePropertyValue 'stopped' -Force
$lensRecord | ConvertTo-Json | Set-Content -LiteralPath $lensRecordPath -Encoding UTF8
Write-Output 'Project emulator stopped; AVD and evidence retained.'
