$ErrorActionPreference = "Stop"
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   SATELLITE CHECKPOINT & QA PROTOCOL     " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

Write-Host "`n[1/2] Ejecutando suite de pruebas automatizada..." -ForegroundColor Yellow
python -m pytest tests/ -v
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[ERROR FATAL] Los tests fallaron. Checkpoint abortado." -ForegroundColor Red
    exit 1
}

Write-Host "[2/2] Telemetria tests/test_report.json generada exitosamente." -ForegroundColor Green
Write-Host "`n==========================================" -ForegroundColor Green
Write-Host "   CHECKPOINT COMPLETADO Y CERTIFICADO    " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
