$ErrorActionPreference = "SilentlyContinue"
$dbCandidates = @(
    "$env:LOCALAPPDATA\ctxfw\tokens.db",
    "$env:USERPROFILE\.ctxfw\ledger.db",
    "C:\ctxfw\tokens.db"
)

$ledgerSummary = "No se detectó base de datos activa."
foreach ($db in $dbCandidates) {
    if (Test-Path $db) {
        $ledgerSummary = sqlite3 $db "SELECT count(*), sum(tokens_saved), sum(cost_saved_usd) FROM audit_ledger;"
        break
    }
}

$prompt = @"
[WEEKLY TELEMETRY FOR SPRINT TRIAGE]
- Git Cloners / Web Views Ratio: 196% (Headless Adoption confirmada)
- Local SQLite Ledger: $ledgerSummary
- Archivos más auditados: SPEC.axioms.md (10) e install.sh (5) vs README.md (8)

Ejecuta el protocolo socrático y destila la propuesta de spec para el siguiente ciclo.
"@

# Inyectar al portapapeles y notificar
Set-Clipboard -Value $prompt
Write-Host " [OK] Telemetria de triaje inyectada al portapapeles." -ForegroundColor Green
Write-Host " Abre Antigravity y presiona Ctrl+V tras invocar /grill-me" -ForegroundColor Cyan
