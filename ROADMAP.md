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

### ⏳ MILESTONE 5: Edge Dinámico (Ponderación por Régimen)
*Estado: ✅ COMPLETADO (2026-02-22) | Timestamp: 19:30*

**Resumen**: Evolución del StrategyRanker hacia un modelo de selección EDGE con ponderación dinámica de métricas. Las métricas se pesan de forma diferente según el régimen de mercado (TREND, RANGE, VOLATILE), permitiendo que estrategias con alto DD pero buen Sharpe sean seleccionadas en contextos volátiles.

- [x] **Field `sharpe_ratio` en tabla `strategy_ranking`**: Integración del índice de rentabilidad/riesgo
  - Implementación: ALTER TABLE migration en `storage.py` (línea 403)
  - Tipo: REAL DEFAULT 0.0
  - Índice creado: idx_strategy_ranking_sharpe (DESC)

- [x] **Tabla `regime_configs` (SSOT)**: Pesos dinámicos por régimen
  - Tabla SQL: CREATE TABLE regime_configs con unique(regime, metric_name)
  - Métodos mixin: `get_regime_weights()`, `get_all_regime_configs()`, `update_regime_weight()`
  - Datos iniciales poblados automáticamente:
    - **TREND**: WR=0.25, Sharpe=0.35, PF=0.30, DD=0.10
    - **RANGE**: WR=0.40, Sharpe=0.25, PF=0.25, DD=0.10
    - **VOLATILE**: WR=0.20, Sharpe=0.50, PF=0.20, DD=0.10

- [x] **Lógica Ponderada en StrategyRanker**: Cálculo de Score Final
  - Método: `calculate_weighted_score(strategy_id, current_regime) → Decimal`
  - Normalización: `_normalize_metrics()` convierte todas las métricas a [0,1]
    - win_rate: ya está [0,1]
    - profit_factor: normalizado por 3.0 (máximo típico)
    - sharpe_ratio: normalizado por 5.0 (máximo realista)
    - drawdown_max: invertido (1 - dd/100) para penalizar DD alto
  - Fórmula: Score = Σ (Métrica_n normalizada × Peso_n)
  - Precisión: Decimal con 4+ decimales (institucional)

- [x] **Integración en Main Orchestrator**: Régimen → StrategyRanker
  - Estructura: `MainOrchestrator` ya cuenta con `self.current_regime`
  - Disponibilidad: Método `calculate_weighted_score()` listo para ser llamado cuando sea necesario
  - Patrón: Inyección de régimen en lugar de hardcoding

- [x] **Test Suite Ponderación**: Validación de lógica de EDGE (10/10 tests passing)
  - Archivo: `tests/test_strategy_weighted_ranking.py`
  - Tests clave:
    - ✅ test_high_dd_good_sharpe_volatile_regime_high_score: DD=5%, Sharpe=2.5 → Score > 0.55 en VOLATILE
    - ✅ test_high_dd_good_sharpe_trend_regime_low_score: Diferente weighting entre regímenes
    - ✅ test_metric_normalization_0_to_1: Todas las métricas normalizadas correctamente
    - ✅ test_weighted_score_calculation_formula: Verificación de fórmula con valores conocidos
    - ✅ test_range_regime_balanced_weights: WR alto recompensado en RANGE
    - ✅ test_regime_comparison_same_strategy: Scores difieren según régimen
    - ✅ test_decimal_precision_institutional_grade: Precisión Decimal validada
    - ✅ test_sharpe_ratio_capped_normalization: Sharpe capped en 5.0
    - ✅ test_missing_sharpe_ratio_defaults_to_zero: Robustez con datos incompletos
    - ✅ test_weights_sum_to_one: Validación de SSOT (suma = 100%)

- [x] **Refactorizaciones Importantes**:
  - Lazy-load del `StorageManager` en `server.py` para evitar inicialización en imports
  - Lazy-load del FastAPI `app` en `server.py` para permitir testing
  - Actualización de `strategy_ranking_db.py`: save_strategy_ranking ahora captura sharpe_ratio
  - Docstring actualizado en StrategyRanker con ejemplos de ponderación

- [x] **Retrocompatibilidad**: 
  - Tests LEGACY de StrategyRanker (promotion/degradation) siguen pasando (9/9 ✅)
  - Métodos existentes: evaluate_and_rank(), batch_evaluate(), etc. sin modificación
  - DB migration: columna sharpe_ratio creada dinámicamente si no existe

**Validación**: Todos los tests NUEVOS (10) + LEGACY (9) pasan correctamente. Sistema listo para producción.

### ⚡ MILESTONE 6: Alpha Institucional (Ineficiencias Pro)
*Próximo Hito*

- [ ] **Detección de FVG (Fair Value Gaps)**: Algoritmo de búsqueda de desequilibrios institucionales.
- [ ] **Arbitraje de Volatilidad**: Detección de desconexión entre Volatilidad Implícita y Realizada.

### 🌐 EXPANSIÓN COMERCIAL & CONECTIVIDAD
- [ ] **Fase SaaS & Multi-Tenancy**: Perfiles de usuario, gestión de suscripciones y aislamiento de DB por cliente.
- [ ] **Capa Institutional (FIX API)**: Conexión directa vía FIX para baja latencia en brokers institucionales.

> [!NOTE]
> El historial completo de hitos anteriores ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).
