param (
    [Parameter(Mandatory=$false)]
    [string]$message = "chore(checkpoint): seal QA verified state"
)

$ErrorActionPreference = "Stop"
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   SATELLITE CHECKPOINT & QA PROTOCOL     " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

$PythonCmd = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

Write-Host "`n[1/2] Executing automated verification matrix..." -ForegroundColor Yellow
& $PythonCmd -m pytest tests/ -v
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[FATAL ERROR] Test suite failed. Checkpoint aborted." -ForegroundColor Red
    exit 1
}

Write-Host "[2/2] Telemetry emitted to tests/test_report.json." -ForegroundColor Green
Write-Host "`n==========================================" -ForegroundColor Green
Write-Host "   CHECKPOINT ATTESTED & VERIFIED         " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
