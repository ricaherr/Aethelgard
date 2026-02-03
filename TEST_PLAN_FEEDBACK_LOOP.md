# TEST DE INTEGRACIÓN: Feedback Loop (TDD - RED PHASE)

## 📋 ESTRUCTURA DEL TEST

```
test_three_losses_trigger_lockdown_and_tuner_adjustment()
│
├─ SETUP
│  └─ Crea RiskManager, EdgeTuner, Storage, Config
│
├─ PHASE 1: SIMULAR 3 TRADES CON PÉRDIDA
│  ├─ Loop i=1,2,3:
│  │  ├─ Crear trade_data (loss: -100 USD)
│  │  ├─ Storage.save_trade_result(trade)
│  │  ├─ RiskManager.record_trade_result(is_win=False, pnl=-100)
│  │  └─ Print: Trade {i} | consecutive_losses={n} | locked={bool}
│  │
│  └─ RESULTADO ESPERADO:
│     Trade 1 → consecutive_losses=1, locked=False
│     Trade 2 → consecutive_losses=2, locked=False
│     Trade 3 → consecutive_losses=3, locked=True ✅ ACTIVA LOCKDOWN
│
├─ PHASE 2: VERIFICAR LOCKDOWN
│  ├─ Assert: consecutive_losses == 3 ✅ PASA
│  ├─ Assert: risk_manager.is_locked() == True ✅ PASA
│  └─ Assert: DB system_state['lockdown_mode'] == True ❌ FALLA
│     Error: "table system_state has no column named updated_at"
│
├─ PHASE 3: TUNER ANALIZA Y AJUSTA
│  ├─ EdgeTuner.adjust_parameters()
│  ├─ Lee trades de DB
│  ├─ Calcula consecutive_losses=3
│  └─ Si >= threshold → Ajusta parámetros (más conservador)
│
├─ PHASE 4: VERIFICAR PARÁMETROS CAMBIARON
│  ├─ Compare initial vs updated params
│  └─ Assert: params_changed == True
│
└─ PHASE 5: RECONCILIACIÓN
   ├─ Simula trades cerradas mientras bot offline
   ├─ Storage.save_trade_result() para 2 trades más
   └─ Assert: get_recent_trades() retorna todas
```

---

## 🔴 ESTADO ACTUAL: RED PHASE

### ✅ LO QUE FUNCIONA
- [x] RiskManager.record_trade_result() incrementa counter
- [x] RiskManager.is_locked() retorna True tras 3 pérdidas
- [x] RiskManager._activate_lockdown() se ejecuta
- [x] Storage.save_trade_result() guarda trades
- [x] Storage.get_recent_trades() recupera trades

### ❌ LO QUE FALLA
1. **Storage schema error**: `table system_state has no column named updated_at`
   - RiskManager intenta: `storage.update_system_state({'lockdown_mode': True})`
   - Pero el método intenta añadir `updated_at` que no existe en tabla
   - **CAUSA**: Problema en el schema de la tabla `system_state`

2. **EdgeTuner threshold mismatch**: 
   - Código actual busca: `if stats["consecutive_losses"] >= 5`
   - Pero RiskManager activa en: `>= 3`
   - **CAUSA**: Desacoplo entre componentes (sin Single Source of Truth)

3. **Dynamic params adjustment verification**:
   - Test espera verificar que parámetros cambiaron
   - Depende de que fase 2 y 3 pasen primero

---

## 🎯 QUÉ NECESITA ARREGLARSE

### Paso 1: Arreglar schema de system_state
- [ ] Revisar método update_system_state() en StorageManager
- [ ] Asegurar que tabla tenga columna `updated_at` o removerla

### Paso 2: Crear Single Source of Truth
- [ ] Crear archivo config/risk_settings.json con max_consecutive_losses=3
- [ ] RiskManager lee de ahí
- [ ] EdgeTuner lee de ahí
- [ ] Eliminar hardcoded 5 en EdgeTuner

### Paso 3: Alinear triggers
- [ ] EdgeTuner: cambiar >= 5 a >= max_consecutive_losses
- [ ] Verificar que ambos componentes usan mismo threshold

---

## 📊 EXPECTED TEST FLOW

```
TEST START
   │
   ├─ Init: capital=10000, consecutive_losses=0, locked=False
   │
   ├─ [PHASE 1] 3 TRADES
   │  ├─ Trade 1 LOSS (-100)  → consecutive_losses=1
   │  ├─ Trade 2 LOSS (-100)  → consecutive_losses=2
   │  └─ Trade 3 LOSS (-100)  → consecutive_losses=3 → LOCKDOWN ACTIVATED
   │                              └─ update_system_state({'lockdown_mode': True}) ✅
   │
   ├─ [PHASE 2] VERIFY LOCKDOWN
   │  ├─ consecutive_losses == 3 ✅
   │  ├─ is_locked() == True ✅
   │  └─ DB state['lockdown_mode'] == True ← FIX NEEDED
   │
   ├─ [PHASE 3] TUNER ADJUST
   │  ├─ get_recent_trades() → 3 trades (all losses)
   │  ├─ _calculate_stats() → consecutive_losses=3
   │  ├─ if 3 >= 3 (after fix): trigger="consecutive_losses"
   │  ├─ adjustment_factor = 1.7 (more conservative)
   │  └─ Save updated dynamic_params.json
   │
   ├─ [PHASE 4] VERIFY PARAMS CHANGED
   │  ├─ ADX: 25 → 42.5 (25 * 1.7)
   │  ├─ ATR: 0.3 → 0.51 (0.3 * 1.7)
   │  ├─ SMA20: 1.5% → 0.88% (1.5 / 1.7)
   │  └─ Score: 60 → 102 (max 80 cap) → 80
   │
   ├─ [PHASE 5] RECONCILIATION
   │  ├─ Save 2 more trades (offline)
   │  ├─ get_recent_trades(limit=100) → 5 trades
   │  └─ Verify all trades recovered
   │
   └─ TEST PASSED ✅
```

---

## 💡 PRÓXIMOS PASOS

1. **Mostrar test creado al usuario** ← AQUÍ ESTAMOS
2. Arreglar schema de system_state
3. Crear risk_settings.json (Single Source of Truth)
4. Actualizar EdgeTuner para usar mismo threshold
5. Ejecutar test nuevamente (debe PASAR)
6. Implementar MainOrchestrator integration hook
7. Actualizar ROADMAP.md

