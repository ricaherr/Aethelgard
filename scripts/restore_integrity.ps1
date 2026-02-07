# 🚨 EMERGENCY RESTORATION PROTOCOL - EXECUTION GUIDE
# ==================================================
# Interactive script to guide user through complete restoration

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "  🚨 AETHELGARD EMERGENCY RESTORATION PROTOCOL" -ForegroundColor Yellow
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""
Write-Host "CRITICAL SITUATION DETECTED:" -ForegroundColor Red
Write-Host "  - Dashboard shows phantom executions (40+)" -ForegroundColor Red
Write-Host "  - Database contaminated with test data" -ForegroundColor Red
Write-Host "  - MT5 shows 0 positions but DB shows trades" -ForegroundColor Red
Write-Host "  - Modules (RiskManager/Executor) frozen" -ForegroundColor Red
Write-Host ""
Write-Host "This protocol will:" -ForegroundColor Green
Write-Host "  1. Purge contaminated data from database" -ForegroundColor Green
Write-Host "  2. Verify MT5 synchronization" -ForegroundColor Green
Write-Host "  3. Diagnose frozen threads" -ForegroundColor Green
Write-Host "  4. Restore system integrity" -ForegroundColor Green
Write-Host ""

# Ask for confirmation
Write-Host "=" * 70 -ForegroundColor Cyan
$confirmation = Read-Host "Do you want to proceed with emergency restoration? (yes/no)"

if ($confirmation -ne "yes") {
    Write-Host ""
    Write-Host "❌ Restoration cancelled. No changes made." -ForegroundColor Yellow
    Write-Host ""
    exit
}

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "  PHASE 1: PRE-DIAGNOSIS" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

# Check integrity before purge
Write-Host "Running integrity check..." -ForegroundColor Yellow
python scripts/check_integrity.py

Write-Host ""
Read-Host "Press Enter to continue to Phase 2 (DATABASE PURGE)"

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "  PHASE 2: DATABASE PURGE" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""
Write-Host "⚠️  WARNING: This will DELETE ALL test data!" -ForegroundColor Red
Write-Host ""

# Execute purge
python scripts/purge_database.py

Write-Host ""
Read-Host "Press Enter to continue to Phase 3 (THREAD DIAGNOSIS)"

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "  PHASE 3: THREAD DIAGNOSIS" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

# Diagnose threads
python scripts/diagnose_threads.py

Write-Host ""
Read-Host "Press Enter to continue to Phase 4 (FINAL VERIFICATION)"

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "  PHASE 4: FINAL VERIFICATION" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

# Run complete verification
python scripts/verify_system.py

Write-Host ""
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "  RESTORATION PROTOCOL COMPLETE" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host ""

Write-Host "Next steps:" -ForegroundColor Green
Write-Host "  1. Review verification results above" -ForegroundColor White
Write-Host "  2. If all checks passed:" -ForegroundColor White
Write-Host "     a) Start system: python main.py" -ForegroundColor Cyan
Write-Host "     b) Open diagnostic UI: streamlit run ui/diagnostic_mode.py" -ForegroundColor Cyan
Write-Host "     c) Monitor for first REAL trade from MT5/Scanner" -ForegroundColor Cyan
Write-Host ""
Write-Host "  3. If checks failed:" -ForegroundColor White
Write-Host "     a) Review error messages above" -ForegroundColor Cyan
Write-Host "     b) Consult scripts/EMERGENCY_PROTOCOL.md" -ForegroundColor Cyan
Write-Host "     c) Re-run this script: .\\scripts\\restore_integrity.ps1" -ForegroundColor Cyan
Write-Host ""

Write-Host "Documentation:" -ForegroundColor Yellow
Write-Host "  - Full protocol: scripts/EMERGENCY_PROTOCOL.md" -ForegroundColor White
Write-Host "  - System rules: AETHELGARD_MANIFESTO.md" -ForegroundColor White
Write-Host "  - Current status: ROADMAP.md" -ForegroundColor White
Write-Host ""
