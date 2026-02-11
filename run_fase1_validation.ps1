# Script de validación automática FASE 1
# Ejecuta tests y validate_all.py

$ErrorActionPreference = "Continue"
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logFile = "validation_fase1_$timestamp.log"

Write-Host "========================================" | Tee-Object -FilePath $logFile
Write-Host "FASE 1 VALIDATION - Position Manager" | Tee-Object -FilePath $logFile -Append
Write-Host "========================================" | Tee-Object -FilePath $logFile -Append
Write-Host "" | Tee-Object -FilePath $logFile -Append

# 1. Git Status
Write-Host "[1/3] Git Status..." | Tee-Object -FilePath $logFile -Append
Write-Host "----------------------------------------" | Tee-Object -FilePath $logFile -Append
git status --short | Tee-Object -FilePath $logFile -Append
Write-Host "" | Tee-Object -FilePath $logFile -Append

# 2. Ejecutar Tests
Write-Host "[2/3] Running pytest tests..." | Tee-Object -FilePath $logFile -Append
Write-Host "----------------------------------------" | Tee-Object -FilePath $logFile -Append
python -m pytest tests\test_position_manager_regime.py -v --tb=short 2>&1 | Tee-Object -FilePath $logFile -Append
$testResult = $LASTEXITCODE
Write-Host "" | Tee-Object -FilePath $logFile -Append

# 3. Ejecutar validate_all
Write-Host "[3/3] Running validate_all.py..." | Tee-Object -FilePath $logFile -Append
Write-Host "----------------------------------------" | Tee-Object -FilePath $logFile -Append
python scripts\validate_all.py 2>&1 | Tee-Object -FilePath $logFile -Append
$validateResult = $LASTEXITCODE
Write-Host "" | Tee-Object -FilePath $logFile -Append

# Resumen
Write-Host "========================================" | Tee-Object -FilePath $logFile -Append
Write-Host "VALIDATION SUMMARY" | Tee-Object -FilePath $logFile -Append
Write-Host "========================================" | Tee-Object -FilePath $logFile -Append
Write-Host "Tests Exit Code: $testResult" | Tee-Object -FilePath $logFile -Append
Write-Host "Validate_all Exit Code: $validateResult" | Tee-Object -FilePath $logFile -Append

if ($testResult -eq 0 -and $validateResult -eq 0) {
    Write-Host "✅ ALL VALIDATIONS PASSED" -ForegroundColor Green | Tee-Object -FilePath $logFile -Append
    exit 0
}
else {
    Write-Host "❌ VALIDATIONS FAILED" -ForegroundColor Red | Tee-Object -FilePath $logFile -Append
    exit 1
}
