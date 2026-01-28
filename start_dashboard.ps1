# Script para iniciar el Dashboard de Aethelgard
# Uso: .\start_dashboard.ps1

Write-Host "🧠 Iniciando Dashboard de Aethelgard..." -ForegroundColor Cyan
Write-Host ""

# Activar entorno virtual
Write-Host "Activando entorno virtual..." -ForegroundColor Yellow
.\venv\Scripts\Activate.ps1

# Verificar Streamlit
$streamlitVersion = python -m streamlit --version 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Streamlit instalado: $streamlitVersion" -ForegroundColor Green
} else {
    Write-Host "✗ Error: Streamlit no está instalado" -ForegroundColor Red
    Write-Host "Instalando Streamlit..." -ForegroundColor Yellow
    pip install streamlit
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Dashboard iniciado en:" -ForegroundColor Green
Write-Host "  http://localhost:8501" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Presiona Ctrl+C para detener el dashboard" -ForegroundColor Yellow
Write-Host ""

# Iniciar dashboard
python -m streamlit run ui/dashboard.py
