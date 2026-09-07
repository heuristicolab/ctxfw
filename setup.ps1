# setup.ps1 — 1-Click Bootstrap Installer for Windows
$ErrorActionPreference = "Stop"

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "   CONTEXT FIREWALL -- ZERO-FRICTION BOOTSTRAP        " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# 1. Virtual Environment Setup
$VenvDir = ".venv"
$VenvPython = "$VenvDir\Scripts\python.exe"
$VenvPip = "$VenvDir\Scripts\pip.exe"

if (!(Test-Path $VenvPython)) {
    Write-Host "`n[1/4] Creating virtual environment (.venv)..." -ForegroundColor Yellow
    python -m venv $VenvDir
} else {
    Write-Host "`n[1/4] Virtual environment (.venv) already exists." -ForegroundColor Green
}

# 2. Dependencies Installation
Write-Host "`n[2/4] Installing dependencies from pyproject.toml..." -ForegroundColor Yellow
& $VenvPython -m pip install --upgrade pip --quiet
& $VenvPython -m pip install -e . --quiet

# 3. Test Certification
Write-Host "`n[3/4] Certifying 51 TDD tests with .venv test runner..." -ForegroundColor Yellow
& $VenvPython -m pytest tests/ -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[ERROR] Test certification failed!" -ForegroundColor Red
    exit 1
}

# 4. Generate Root firewall.cmd
Write-Host "`n[4/4] Generating root CLI wrapper (firewall.cmd)..." -ForegroundColor Yellow
$CmdContent = @"
@echo off
"%~dp0.venv\Scripts\python.exe" "%~dp0firewall_cli.py" %*
"@

Set-Content -Path "firewall.cmd" -Value $CmdContent -Encoding ASCII

Write-Host "`n======================================================" -ForegroundColor Green
Write-Host "   BOOTSTRAP COMPLETE & CERTIFIED (51/51 PASSED)      " -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
Write-Host "You can now execute directly from anywhere in the repo:" -ForegroundColor White
Write-Host "  .\firewall contracts.py`n" -ForegroundColor Yellow
