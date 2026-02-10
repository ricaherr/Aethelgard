# Test System - Clean Launch
Write-Host "🧪 Aethelgard System Test - Clean Launch" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Kill any existing Python processes
Write-Host "`n🔪 Matando procesos Python existentes..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Clean .pyc files NEW
Write-Host "🧹 Limpiando archivos .pyc..." -ForegroundColor Yellow
Get-ChildItem -Path . -Include *.pyc -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path . -Include __pycache__ -Recurse -Force -ErrorAction SilentlyContinue | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue

Write-Host "`n🚀 Iniciando sistema..." -ForegroundColor Green

# Run system and save logs
python start.py 2>&1 | Tee-Object -FilePath "system_test.log"
