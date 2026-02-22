# AETHELGARD: ESTRATEGIC ROADMAP

**Versión Log**: 2.5.0 (Shadow Ranking & Darwinismo Algorítmico)
**Última Actualización**: 21 de Febrero, 2026 (XX:XX)

---

## 🏗️ MILESTONE: Auditoría, Limpieza & Cerebro Console (2026-02-21)
**Estado: ✅ COMPLETADO**
**Resumen**: Refactorización profunda de documentación (`docs/`), revitalización de la Cerebro Console (UI/UX), implementación de Monitor a pantalla completa y corrección de errores de renderizado críticos (Error #31).
- **Monitor de Integridad L3**: Diagnóstico profundo de fallos con captura de excepciones.
- **Protocolo de Auto-Gestión L1**: Puente para reparaciones autónomas (Inactivado para validación).

---

## 📈 ROADMAP ESTRATÉGICO (Próximos Hitos)

### ✅ MILESTONE 3: Universal Trading Foundation (Agnosticismo & Normalización)
*Estado: ✅ COMPLETADO (2026-02-21) | Timestamp: 18:25*

- [x] **Tabla `asset_profiles` (SSOT)**: Creación de la base de datos maestra para normalizar Tick Size, Contract Size, Lot Step y Comisiones por activo.
  - Implementación: `data_vault/market_db.py` & `data_vault/storage.py`
  - Datos iniciales: EURUSD, GBPUSD, USDJPY, GOLD, BTCUSD
  - Validación: ✅ Test suite completo (289/289 tests pass)

- [x] **Cálculo Universal (Unidades R)**: Refactorización agnóstica del `RiskManager.calculate_position_size()` con precisión institucional.
  - Aritmética: `Decimal` para evitar errores de punto flotante
  - Redondeo: Downward rounding (ROUND_DOWN) según `lot_step` del activo
  - Trazabilidad: Cada cálculo genera Trace_ID único (ej: NORM-0a9dfe65)
  - Seguridad: `AssetNotNormalizedError` si símbolo no existe en `asset_profiles`

- [x] **Normalización SSOT & Testing**: Validación completa con precisión decimal.
  - Script: `scripts/utilities/test_asset_normalization.py`
  - Resultado: TODOS LOS TESTS PASARON (6/6 validaciones OK)

### ✅ MILESTONE 4: Estratega Evolutivo (Darwinismo Algorítmico)
*Estado: ✅ COMPLETADO (2026-02-21) | Timestamp: Post-Asset Normalization*

**Resumen**: Implementación del motor de Shadow Ranking System. El sistema ahora clasifica estrategias en 3 modos (SHADOW, LIVE, QUARANTINE) y ejecuta solo aquellas autorizadas en base a métricas de rentabilidad y riesgo.

- [x] **Shadow Ranking System**: Sistema de evolución de estrategias con Trace_ID auditado.
  - Tabla DB: `strategy_ranking` con campos: profit_factor, win_rate, drawdown_max, consecutive_losses, execution_mode
  - Mixin: `StrategyRankingMixin` en `data_vault/strategy_ranking_db.py`
  - Integración: `StorageManager` accede a rankings para auditoría persistente

- [x] **Motor de Promoción/Degradación**: `StrategyRanker` en `core_brain/strategy_ranker.py`
  - Promoción (SHADOW → LIVE): Profit Factor > 1.5 AND Win Rate > 50% en últimas 50 ops
  - Degradación (LIVE → QUARANTINE): Drawdown >= 3% OR Consecutive Losses >= 5
  - Recuperación (QUARANTINE → SHADOW): Métricas normalizadas tras N ciclos de mejora

- [x] **Integración en Pipeline de Ejecución**: `MainOrchestrator._is_strategy_authorized_for_execution()`
  - Antes de ejecutar cada orden, verifica `strategy_ranking.execution_mode`
  - Solo LIVE strategies generan órdenes reales
  - SHADOW strategies rastrean métricas sin ejecutar
  - QUARANTINE strategies bloqueadas hasta recuperación

- [x] **Auditoría y Trazabilidad**: Trace_ID único (RANK-XXXXXXXX) para cada transición de estado
  - Logging persistente en `edge_learning` tabla
  - Contexto completo de métricas en cada cambio de modo

- [x] **Test Suite Completa**: 9/9 tests unitarios pasando
  - `tests/test_strategy_ranker.py`: Promoción, degradación, recuperación, auditoría
  - Coverage: Todos los caminos de lógica validados

### ⚡ MILESTONE 5: Alpha Institucional (Ineficiencias Pro)
*Próximo Hito*

- [ ] **Detección de FVG (Fair Value Gaps)**: Algoritmo de búsqueda de desequilibrios institucionales.
- [ ] **Arbitraje de Volatilidad**: Detección de desconexión entre Volatilidad Implícita y Realizada.

### 🌐 EXPANSIÓN COMERCIAL & CONECTIVIDAD
- [ ] **Fase SaaS & Multi-Tenancy**: Perfiles de usuario, gestión de suscripciones y aislamiento de DB por cliente.
- [ ] **Capa Institutional (FIX API)**: Conexión directa vía FIX para baja latencia en brokers institucionales.

> [!NOTE]
> El historial completo de hitos anteriores ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).
