# AETHELGARD: SPRINT LOG

**Última Actualización**: 9 de Abril, 2026 (SRE Audit completada — E18 iniciada)

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Diario de ejecución. Cada Sprint referencia una Épica del ROADMAP y las HUs del BACKLOG que ejecuta.
> - **Estructura**: `Sprint NNN: [nombre]` → tareas con referencia `HU X.Y` → snapshot de cierre.
> - **Estados únicos permitidos**: `[TODO]` · `[DEV]` · `[DONE]`
> - **`[DONE]`** solo si `validate_all.py` ✅ 100% ejecutado y pasado.
> - **Al cerrar Sprint**: snapshot de métricas + actualizar HUs en BACKLOG a `[DONE]` + archivar en SYSTEM_LEDGER.
> - **PROHIBIDO**: `[x]`, `[QA]`, `[IN_PROGRESS]`, `[CERRADO]`, `[ACTIVO]`, `✅ COMPLETADA`
> - **Framework completo**: `.ai_orchestration_protocol.md` Sección 4.

---

# SPRINT 28: E18 — SRE REPARACIÓN Y ESTABILIZACIÓN OPERACIONAL — [TODO]

**Inicio**: 9 de Abril, 2026
**Fin**: —
**Objetivo**: Reparar el pipeline operacional bloqueado. La auditoría SRE del 09-Apr confirmó que el sistema es un zombie operacional: 3 estrategias en modo SHADOW según `sys_strategies.mode` (SSOT) pero en modo BACKTEST según `sys_signal_ranking.execution_mode` (campo derivado desactualizado). Resultado: 0 señales ejecutadas, 0 shadow trades, 6 instancias shadow atrapadas en INCUBATING. Este sprint repara los 5 defectos documentados en E18.
**Épica**: E18 (SRE — Reparación y Estabilización Operacional) | **Trace_ID**: E18-SRE-OPERATIONAL-REPAIR-2026-04-09
**Dominios**: 08_DATA_SOVEREIGNTY · 10_INFRASTRUCTURE_RESILIENCY · 09_INSTITUTIONAL_INTERFACE

## 📋 Tareas del Sprint

- [DONE] **HU 8.8: SSOT Execution Mode Drift Fix** *(🔴 PRIORIDAD MÁXIMA — Bloqueante de todo lo demás)*
  - Implementado por ejecutor en 3 archivos de producción + 1 archivo de tests.
  - Verificación orquestador: `pytest tests/test_ssot_execmode_drift.py -q` = 7/7 PASS.
  - Verificación orquestador: `python scripts/validate_all.py` = 28/28 PASS.
  - Verificación funcional: `_get_execution_mode` retorna SHADOW para MOM_BIAS_0001, LIQ_SWEEP_0001 y STRUC_SHIFT_0001.

- [TODO] **HU 10.24: Shadow Pool Bootstrap Diagnostics**
  - En `core_brain/orchestrators/_discovery.py`: el branch `already_active >= variations_per_strategy` debe incrementar `skipped_count`.
  - Agregar log `INFO` que diferencie "skipped: not SHADOW mode" de "skipped: already at max instances".
  - Test: verificar que el resumen reporta correctamente cuando todas las instancias existen.

- [DONE] **HU 10.25: Health Endpoint SRE**
  - Crear `GET /health` en el router FastAPI que retorne: `status`, `orchestrator_heartbeat_age_s`, `last_signal_at`, `last_trade_at`, `operational_mode`, `active_strategies`.
  - Sin autenticación. Sin datos sensibles del usuario. Respuesta en <50ms.
  - Test: `GET /health` retorna HTTP 200 con JSON válido en cualquier estado del sistema.
  - Verificación orquestador: `pytest tests/test_health_endpoint.py -q` = 4/4 PASS.
  - Verificación orquestador: `python scripts/validate_all.py` = 28/28 PASS.
  - Verificación runtime: `GET /health` responde HTTP 200 con payload estable y `status=ok` en arranque normal.

- [DONE] **HU 10.26: Heartbeat Audit Trail Repair**
  - Se endureció `update_module_heartbeat` para garantizar primer write auditado por arranque/componente y mantener throttle en subsiguientes writes.
  - OEM ahora prioriza heartbeat de `sys_audit_logs` cuando es más reciente o utilizable; fallback controlado a `sys_config`.
  - Verificación orquestador: `pytest tests/test_heartbeat_audit_trail.py tests/test_module_heartbeat_audit.py tests/test_oem_heartbeat_check.py tests/test_system_db_heartbeat_canonical.py -q` = 22/22 PASS.
  - Verificación orquestador: `python scripts/validate_all.py` = 28/28 PASS.
  - Verificación runtime: `python start.py` inició sin crash y mantuvo loop operacional activo durante ventana de verificación.

- [TODO] **HU 9.9: UI Confidence Display Overflow Fix**
  - Confirmar el rango de retorno de `market_structure_analyzer._calculate_confidence_score_professional()` (debe ser 0-100).
  - Rastrear por qué el valor llega a `_cycle_scan.py:466` como 558 en lugar de 55.8.
  - Corregir el punto donde ocurre la escala errónea.

---

## ETI SPEC — HU 8.8: SSOT Execution Mode Drift Fix

**Trace_ID**: `SSOT-EXECMODE-DRIFT-FIX-2026-04-09`
**Archivos afectados**:
- `data_vault/sys_signal_ranking_db.py` (método `_get_mode_from_sys_strategies`, `ensure_signal_ranking_for_strategy`)
- `core_brain/services/strategy_engine_factory.py` (método `_get_execution_mode`)
- `data_vault/schema.py` (migración: sincronizar entradas existentes)
- `tests/test_strategy_engine_factory.py` (nuevo archivo de test TDD)

---

### 1. Problema

**Estado actual:**
- `sys_strategies.mode` (SSOT canónico) = `'SHADOW'` para MOM_BIAS_0001, LIQ_SWEEP_0001, STRUC_SHIFT_0001
- `sys_signal_ranking.execution_mode` (campo derivado) = `'BACKTEST'` para las mismas — congelado en lazy-init del 05-Apr-2026
- `StrategyEngineFactory._get_execution_mode()` llama a `ensure_signal_ranking_for_strategy()` que retorna el registro existente de `sys_signal_ranking` con `'BACKTEST'`
- `is_strategy_authorized_for_execution()` en `_lifecycle.py` retorna `False` para BACKTEST → ninguna estrategia ejecuta
- Shadow pool: 6 instancias en INCUBATING, `total_trades_executed = 0`, sin movimiento

**Estado deseado:**
- `_get_execution_mode()` lee siempre de `sys_strategies.mode` (SSOT único)
- `sys_signal_ranking.execution_mode` se actualiza solo al cambiar de modo (por ranking/promoción), no es fuente de verdad para el routing
- `is_strategy_authorized_for_execution()` recibe `'SHADOW'` → retorna `True` → shadow trades inician
- Entradas en `sys_signal_ranking` existentes se migran para alinear con `sys_strategies.mode`

---

### 2. Análisis Técnico / Decisiones de Diseño

**Por qué existe el drift:**
`_get_mode_from_sys_strategies()` se llama UNA SOLA VEZ durante el lazy-init de `ensure_signal_ranking_for_strategy()`. Una vez que la entrada existe en `sys_signal_ranking`, nunca se vuelve a sincronizar. Si `sys_strategies.mode` cambia posteriormente (de 'BACKTEST' a 'SHADOW' por una actualización manual), el drift queda silenciado.

**Dos campos, un concepto — violación sutil de .ai_rules.md §2.5:**
- `sys_strategies.mode` = estado de ciclo de vida de la estrategia (admin-configurable, SSOT)
- `sys_signal_ranking.execution_mode` = fue concebido como "modo de ejecución en tiempo real" para el StrategyRanker, pero en la práctica es el mismo concepto. Duplicación innecesaria.

**Alternativas evaluadas:**

| Opción | Pros | Contras | Selección |
|---|---|---|---|
| A: `_get_execution_mode()` siempre lee de `sys_strategies.mode` | SSOT puro, elimina drift | Requiere cambio en factory + test | **Elegida** |
| B: Trigger SQL que sincroniza `sys_signal_ranking` cuando cambia `sys_strategies.mode` | Automático | SQLite no soporta triggers multi-tabla bien; magia oculta | Descartada |
| C: Eliminar `execution_mode` de `sys_signal_ranking` | Reduce campos | Breaking change mayor en StrategyRanker + schema | Deuda técnica futura, no ahora |

**Decisión final**: Opción A + migración de datos existentes. La factory debe ser la única que lee `sys_strategies.mode` para routing. El campo `sys_signal_ranking.execution_mode` sigue siendo útil para el `StrategyRanker` al registrar promociones históricas, pero no es la fuente de verdad para decidir si una estrategia puede ejecutar.

**Restricciones de stack:**
- No se puede usar `ALTER TABLE DROP COLUMN` en SQLite < 3.35 — verificar versión o usar migración de rename
- El cambio en factory es local y no rompe la interfaz pública
- La migración debe ser aditiva y no destructiva (`.ai_rules.md §2.3`)

---

### 3. Solución

**Parte A — Cambio en `strategy_engine_factory.py`:**

```python
def _get_execution_mode(self, strategy_id: str) -> str:
    """
    Reads execution mode from sys_strategies (SSOT).
    sys_signal_ranking.execution_mode is NOT the source of truth for routing.
    """
    try:
        # SSOT: sys_strategies.mode (not sys_signal_ranking)
        mode = self.storage.get_strategy_lifecycle_mode(strategy_id)
        if mode in ("SHADOW", "LIVE", "QUARANTINE", "BACKTEST"):
            return mode
        logger.warning(
            "[FACTORY] %s: Unknown mode '%s' from sys_strategies.mode — defaulting to SHADOW",
            strategy_id, mode
        )
        return "SHADOW"
    except Exception as e:
        logger.error("[FACTORY] %s: Error reading strategy mode: %s", strategy_id, e)
        return "SHADOW"
```

**Parte B — Nuevo método en `sys_signal_ranking_db.py`:**

```python
def get_strategy_lifecycle_mode(self, strategy_id: str) -> str:
    """
    Returns sys_strategies.mode (SSOT) for a given strategy.
    Used by StrategyEngineFactory for routing decisions.
    Returns 'SHADOW' if not found (safe default).
    """
    conn = self._get_conn()
    try:
        row = conn.execute(
            "SELECT mode FROM sys_strategies WHERE class_id = ?",
            (strategy_id,)
        ).fetchone()
        return str(row[0]) if row and row[0] else "SHADOW"
    except Exception as e:
        logger.error("[DB] get_strategy_lifecycle_mode failed for %s: %s", strategy_id, e)
        return "SHADOW"
    finally:
        self._close_conn(conn)
```

**Parte C — Migración de datos en `schema.py` `run_migrations()`:**

```python
# Migration: sync sys_signal_ranking.execution_mode with sys_strategies.mode (SSOT)
# Fixes SSOT drift caused by lazy-init on 2026-04-05
conn.execute("""
    UPDATE sys_signal_ranking
    SET execution_mode = (
        SELECT s.mode FROM sys_strategies s WHERE s.class_id = sys_signal_ranking.strategy_id
    ),
    trace_id = 'SSOT-SYNC-MIGRATION-2026-04-09',
    updated_at = CURRENT_TIMESTAMP
    WHERE EXISTS (
        SELECT 1 FROM sys_strategies s
        WHERE s.class_id = sys_signal_ranking.strategy_id
        AND s.mode != sys_signal_ranking.execution_mode
    )
""")
```

---

### 4. Cambios por Archivo

| Archivo | Cambio | Tipo |
|---|---|---|
| `core_brain/services/strategy_engine_factory.py` | `_get_execution_mode()`: reemplaza llamada a `ensure_signal_ranking_for_strategy()` por nueva `get_strategy_lifecycle_mode()` | Modificación |
| `data_vault/sys_signal_ranking_db.py` | Agregar método `get_strategy_lifecycle_mode(strategy_id)` | Adición |
| `data_vault/schema.py` | Agregar migración SQL idempotente en `run_migrations()` que sincroniza `sys_signal_ranking.execution_mode` desde `sys_strategies.mode` | Modificación |
| `tests/test_ssot_execmode_drift.py` | Nuevo archivo con 5 tests TDD | Creación |

**Archivos NO modificados**: `core_brain/orchestrators/_lifecycle.py`, `core_brain/orchestrators/_discovery.py`, `core_brain/shadow_manager.py` — estos consumen el modo y deben funcionar correctamente una vez que la fuente correcta sea leída.

---

### 5. Criterios de Aceptación

1. `_get_execution_mode("MOM_BIAS_0001")` retorna `'SHADOW'` (de `sys_strategies.mode`)
2. `_get_execution_mode("BRK_OPEN_0001")` retorna `'BACKTEST'` (sus sys_strategies.mode es BACKTEST)
3. La migración en `run_migrations()` actualiza las 3 entradas en `sys_signal_ranking` de BACKTEST a SHADOW
4. `initialize_shadow_pool_impl` no crea instancias extra (ya existen 2 por estrategia) — comportamiento esperado
5. En el arranque, los logs muestran `SHADOW mode` para las 3 estrategias en lugar de `BACKTEST mode`
6. `validate_all.py` 28/28 PASS
7. `start.py` arranca sin regresiones

---

### 6. Tests TDD (archivo: `tests/test_ssot_execmode_drift.py`)

```python
# Test 1 (happy path): SHADOW strategy returns SHADOW
# Test 2 (happy path): BACKTEST strategy returns BACKTEST
# Test 3 (edge case): strategy not in sys_strategies returns SHADOW (safe default)
# Test 4 (edge case): DB error in get_strategy_lifecycle_mode returns SHADOW (safe default)
# Test 5 (migration): run_migrations() syncs divergent sys_signal_ranking.execution_mode
```
*(Implementar en TDD: crear los tests primero, luego el código)*

---

### 7. Riesgos

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| `storage` no expone `get_strategy_lifecycle_mode` — falla en inyección | Media | Verificar herencia de StorageManager antes de implementar |
| Migración puede sobrescribir cambios manuales recientes en `sys_signal_ranking` | Baja | La cláusula `WHERE s.mode != execution_mode` es condicional; documentar en trace_id |
| Estrategias LOGIC_PENDING tienen `sys_strategies.mode = 'SHADOW'` — podrían activarse | Alta | Confirmar que el bloqueo por `readiness=LOGIC_PENDING` ocurre ANTES de que se evalúe el modo |

**Verificación del riesgo 3**: En `_load_single_strategy()`, el check de `readiness == "LOGIC_PENDING"` ocurre en líneas 140-145, ANTES de llamar a `_get_execution_mode()` en línea ≈160. El orden es correcto — las estrategias LOGIC_PENDING nunca llegan a la lectura del modo.

---

### 8. Orden de Ejecución

```
1. Crear tests/test_ssot_execmode_drift.py con 5 tests (TDD — deben FALLAR primero)
2. Agregar get_strategy_lifecycle_mode() en data_vault/sys_signal_ranking_db.py
3. Modificar _get_execution_mode() en strategy_engine_factory.py
4. Agregar migración en data_vault/schema.py run_migrations()
5. Ejecutar tests → deben PASAR
6. Ejecutar validate_all.py → 28/28
7. Ejecutar start.py → confirmar logs muestran SHADOW mode para las 3 estrategias
8. Confirmar sys_signal_ranking.execution_mode actualizado en DB post-arranque
```

---



**Inicio**: 8 de Abril, 2026
**Fin**: —
**Objetivo**: Completar la jerarquía de acceso SaaS (3 tiers + SSOT fix), implementar correlación inter-mercado para señales de alta fidelidad, el motor Shadow Reality con penalización real de latencia/slippage, y el ranking darwinista de estrategias por tenant con UI.
**Épica**: E16 (Membresía SaaS, Correlación Multi-Mercado & Darwinismo de Portafolio) | **Trace_ID**: E16-SAAS-PORTFOLIO-DARWIN-2026
**Dominios**: 01_IDENTITY_SECURITY · 03_ALPHA_GENERATION · 06_PORTFOLIO_INTELLIGENCE · 08_DATA_SOVEREIGNTY

## 📋 Tareas del Sprint

- [TODO] **HU 1.3: User Role & Membership Level** *(🔴 PRIORIDAD MÁXIMA — Deuda Técnica)*
  - Agregar tercer tier (`INSTITUTIONAL` o `ADMIN`) al enum `MembershipLevel` en `module_manager.py`.
  - Eliminar fallback a `modules.json`: `get_modules_config()` debe leer EXCLUSIVAMENTE de DB (`StorageManager`).
  - Sincronizar `sys_users.tier` con el nuevo enum (migración de schema si aplica).
  - Implementar endpoint REST `GET /api/profile/membership` → devuelve tier actual + módulos desbloqueados/bloqueados.
  - Construir componente React "Membership Badge" en menú de perfil UI con feature visibility.

- [TODO] **HU 3.3: Multi-Market Alpha Correlator**
  - Diseñar `MultiMarketCorrelator` en `core_brain/` que correlacione señales activas entre activos (FOREX, índices, commodities).
  - Implementar índice de confluencia inter-mercado: si 3+ activos correlacionados emiten misma dirección, boost de confianza de señal.
  - Exponer vía endpoint REST `GET /api/alpha/correlations`.
  - Widget UI "Correlación Sistémica" con indicadores de fuerza y dirección multi-activo.

- [TODO] **HU 6.1: Shadow Reality Engine (Penalty Injector)**
  - Implementar `ShadowRealityEngine` que aplique latencia simulada y slippage real histórico al P&L de estrategias SHADOW.
  - Ajustar métricas de `StrategyRanker` para usar P&L penalizado (no teórico) en decisiones de promoción.
  - Exponer endpoint `GET /api/portfolio/shadow-equity/{strategy_id}` con curva "Shadow vs Theory".
  - Gráfico UI "Shadow vs Theory Equity Curve" con desglose de pips perdidos por ineficiencia.

- [TODO] **HU 6.2: Multi-Tenant Strategy Ranker**
  - Implementar `get_rankings_for_user(user_id: str)` en `StrategyRanker` que filtre rankings por estrategias activas del tenant.
  - Implementar endpoint REST `GET /api/portfolio/rankings` (autenticado, devuelve ranking personalizado por JWT user).
  - Dashboard React "Strategy Darwinism" con tabla de rankings dinámicos y badges de estado (SHADOW/LIVE/QUARANTINE) por trader.

- [DONE] **HU 8.4: Enforcement de Persistencia (DB Policy Root-Fix)**
  - Guard runtime instalado en `start.py`: bloquea nuevas conexiones `sqlite3.connect` fuera de rutas aprobadas (lista allowlist + legacy baseline).
  - Auditoría AST automática `scripts/utilities/runtime_persistence_audit.py` integrada en `validate_all.py` (Domain 08).
  - Baseline generado: 99 violaciones congeladas en `governance/baselines/runtime_persistence_baseline.json` (4 sqlite_connect + 95 manual_commit).
  - 4/4 tests focalizados passing · `validate_all.py` 28/28 · `start.py` smoke OK · 2334/2337 global suite.
  - Bypass pytest activo (`PYTEST_CURRENT_TEST` / `sys.modules["pytest"]`) para no bloquear suite de desarrollo.
  - Trace_ID: `DB-POLICY-RUNTIME-ENFORCEMENT-2026-04-07`

- [DONE] **HU 8.5: Migración de Writes Bypass a Contrato de Driver**
  - Migrados 5 métodos en `data_vault/market_db.py`: `log_sys_market_pulse`, `log_coherence_event`, `_clear_ghost_position_inline`, `log_market_cache`, `seed_initial_assets` → `with self.transaction()`.
  - Migrados 4 métodos en `data_vault/storage.py`: `save_coherence_event`, `update_user_config`, `append_to_system_ledger`, `save_economic_event` → `with self.transaction()`.
  - 18/18 tests focalizados (test_market_db_write_contract + test_storage_write_contract) · 2352/2355 global suite · validate_all.py 28/28.
  - Baseline reducido: 99 → 90 violaciones (9 manual_commit eliminados). Nuevo freeze generado.
  - Trace_ID: `DB-POLICY-RUNTIME-WRITES-HU8.5-2026-04-07`

- [DONE] **HU 10.21: Hardening de Arranque y Señales de Consola**
  - Clasificar warnings/errores de arranque por severidad operativa real (esperado vs degradación vs fallo crítico).
  - Ajustar logs de fallback no fatal en conectores y sensores (`mt5_data_provider`, `ctrader_connector`, `session_liquidity_sensor`, `signal_factory`).
  - Ajustar StrategyEngineFactory para que bloques esperados por gobernanza (`LOGIC_PENDING`) se registren como `warning` y no como `error`.
  - Validación obligatoria: `start.py` (sin errores espurios) + `pytest -q` + `scripts/validate_all.py`.
  - Trace_ID: `LOG-HARDENING-STARTUP-2026-04-08`

- [DONE] **HU 8.6: Migración de Writes Legacy SystemMixin**
  - Migrados 13 métodos en `data_vault/system_db.py`: `save_tuning_adjustment`, `save_data_provider`, `update_provider_enabled`, `set_connector_enabled`, `update_usr_notification_settings`, `save_notification`, `mark_notification_read`, `delete_old_notifications`, `save_symbol_mapping`, `update_usr_preferences`, `update_dedup_rule`, `mark_orphan_shadow_instances_dead`, `update_strategy_execution_params` → `with self.transaction()`.
  - 13 nuevos tests de regresión en `tests/test_storage_sqlite.py` · 20/20 passing · `validate_all.py` 28/28.
  - Baseline actualizado: 90 → 76 violaciones (reducción de 14). Nuevo freeze generado.
  - Smoke test `start.py` limpio: sin `SystemError`, sin `commit returned NULL`.
  - Trace_ID: `DB-POLICY-SYSTEM-MIXIN-WRITES-HU8.6-2026-04-08`

- [DONE] **HU 8.7: Eliminación de Doble-Commit en callbacks serializados**
  - Eliminados `conn.commit()/rollback()` manuales dentro de callbacks `_execute_serialized` en `data_vault/signals_db.py`, `data_vault/execution_db.py`, `data_vault/broker_accounts_db.py`.
  - Hardening de `DatabaseManager`: limpieza de `_tx_lock_pool` al cerrar conexión y en `shutdown` para evitar crecimiento residual.
  - Tests nuevos de contrato en `tests/test_database_driver_contract.py` para prohibir commits manuales en callbacks serializados y validar limpieza de lock pool.
  - Validación: 45/45 tests focalizados · `validate_all.py` 28/28 · `start.py` sin `EDGE TEST ERROR` ni `cannot commit - no transaction is active`.
  - Baseline runtime persistence reducido: 76 → 66 violaciones (sin nuevas violaciones vs baseline).
  - Trace_ID: `DB-POLICY-SERIALIZED-CALLBACKS-HU8.7-2026-04-08`

- [DONE] **HU 10.22: Grace Window OEM para Invariantes de Bootstrap**
  - `core_brain/operational_edge_monitor.py`: agregado `STARTUP_INVARIANT_GRACE_SECONDS_DEFAULT=300`, checks objetivo `{shadow_sync, lifecycle_coherence}` y normalización FAIL->WARN durante bootstrap.
  - Se aplica la gracia tanto en `run()` como en `get_health_summary()` para alinear runtime y API.
  - Tests de contrato actualizados: `tests/test_oem_repair_flags.py` y `tests/test_operational_edge_monitor.py`.
  - Validación: 62/62 tests OEM focalizados · `validate_all.py` 28/28.
  - Evidencia runtime: `logs/main.log` registra `Startup grace active (299s remaining)` en arranque reciente y sin `Invariant violations: shadow_sync, lifecycle_coherence` en ese bootstrap.
  - Trace_ID: `OEM-STARTUP-GRACE-HU10.22-2026-04-08`

- [DONE] **HU 10.23: Hardening OEM Post-Bootstrap (No-Accionables Reales)**
  - `core_brain/operational_edge_monitor.py`: `shadow_sync` ahora distingue `INCUBATING` (dentro/fuera de ventana) y casos no accionables por estrategia; `lifecycle_coherence` usa `last_update_utc` como fuente primaria y degrada stale bootstrap sin historial (`total_usr_trades=0`, `completed_last_50=0`).
  - Mantiene FAIL solo para bloqueos accionables; casos no accionables pasan a WARN/OK.
  - TDD ampliado en `tests/test_operational_edge_monitor.py` y contrato de flags en `tests/test_oem_repair_flags.py`.
  - Validación: 69/69 tests OEM focalizados · `validate_all.py` 28/28.
  - Evidencia runtime: `logs/main.log` muestra `All checks passed (warnings=6)` fuera de gracia en ciclos consecutivos (sin `Invariant violations: shadow_sync, lifecycle_coherence`).
  - Trace_ID: `OEM-POST-BOOTSTRAP-HARDENING-HU10.23-2026-04-08`

- [DONE] **REFACTOR-001: DRY Consolidation — Symbol Taxonomy SSOT** *(Technical Refactoring — No HU formal)*
  - Creado `core_brain/symbol_taxonomy_engine.py` (~200 líneas): clase `SymbolTaxonomy` con métodos estáticos puros `get_symbol_type()` e `is_index_without_volume()`.
  - Eliminado `DataProviderManager._detect_symbol_type()` (~30 líneas) — refactorizado a usar `SymbolTaxonomy.get_symbol_type()`.
  - Eliminado hardcoded `index_no_volume_symbols` en `MarketStructureAnalyzer` — refactorizado a usar `SymbolTaxonomy.is_index_without_volume()`.
  - Implementado contrato de invariantes (disjunción de sets, INDICES_WITHOUT_VOLUME ⊆ INDICES, pureza funcional).
  - Tests nuevos: `test_symbol_taxonomy_engine.py` (15/15 PASSED) — clasificación, invariantes, edge cases.
  - Tests de regresión: `test_data_provider_manager.py` (20/20), `test_market_structure_analyzer.py` (15/15) — **CERO regresiones**.
  - Validación: **51/51 tests** (taxonomy + regresión) · `validate_all.py` **28/28 PASSED** · `start.py` booteable sin errores críticos.
  - **Net changesum**: Consolidación pura (SSOT closure, DRY violation eliminada, testabilidad mejorada, zero new logic).
  - Trace_ID: `DRY-SYMBOL-TAXONOMY-SSOT-2026-04-09`

## 📊 Snapshot de Cierre

*(Se completa cuando el sprint finaliza)*

---

# SPRINT 26: E15 — PERSISTENCIA AGNÓSTICA & TELEMETRÍA BROKER-NEUTRAL — [DONE]

**Inicio**: 6 de Abril, 2026
**Fin**: 7 de Abril, 2026
**Objetivo**: Resolver bloqueo DB en SQLite sin anti-patrones de embudo global y eliminar dependencias hardcoded a MT5 en telemetría/salud, preservando escalabilidad hacia Postgres/MySQL.
**Épica**: E15 (Persistencia Agnóstica & Telemetría Broker-Neutral) | **Trace_ID**: ARCH-DB-DRIVER-AGNOSTIC-MT5-DECOUPLING-2026-04-06
**Dominios**: 08_DATA_SOVEREIGNTY · 10_INFRASTRUCTURE_RESILIENCY

## 📋 Tareas del Sprint

- [DONE] **HU 10.20: Telemetría agnóstica de proveedor (sin dependencia MT5 hardcoded)**
  - Refactor de `start.py` para reducir inyecciones directas orientadas a MT5 en componentes de flujo general.
  - Revisión de chequeos de runtime para basar disponibilidad en proveedor activo/capabilidades, no en broker nominal.
  - Ajuste de tareas de background que asumen `ConnectorType.METATRADER5` como fuente única.

- [DONE] **HU 8.2: Contrato de Persistencia Agnóstica (IDatabaseDriver + adapters)**
  - Definir interfaz de driver de datos y adaptar `StorageManager` a delegación por backend.
  - Mantener contrato estable para mixins/repositorios existentes.
  - Preparar pathway para adapter SQL robusto (sin cola forzada).

- [DONE] **HU 8.3: Concurrencia SQLite híbrida (retry/backoff + cola selectiva)**
  - Implementar estrategia anti-lock en adapter SQLite sin serialización total del Core.
  - Aplicar cola selectiva a telemetría/eventos de alta frecuencia donde tenga sentido operativo.
  - Preservar throughput y semántica transaccional en operaciones críticas.

## 📊 Snapshot de Cierre

- **HU 10.20**: [DONE] — Telemetría agnóstica MT5 (completada Sprint 26 apertura)
- **HU 8.2**: [DONE] — Contrato IDatabaseDriver + SQLiteDriver + errores normalizados · 6/6 tests · `validate_all.py` 27/27 · `start.py` sin regresión · Trace_ID: `ARCH-DB-DRIVER-AGNOSTIC-HU8.2-2026-04-07`
- **HU 8.3**: [DONE] — Retry/backoff acotado + cola selectiva de telemetría + métricas de concurrencia + bypass bootstrap/migraciones · 7/7 tests HU 8.3
- **Suite focalizada HU 8.2+8.3**: 14/14 PASSED
- **Validación integral**: `validate_all.py` 27/27 PASSED
- **Smoke de arranque**: `start.py` sin fallo fatal atribuible a E15
- **Estado Sprint 26**: [DONE] — E15 implementada end-to-end

---

# SPRINT 25: EDGE IGNITION PHASE 5 & 6 — SELF-HEALING, CORRELATION ENGINE & RESILIENCE UI — [DONE]

**Inicio**: 31 de Marzo, 2026
**Fin**: 5 de Abril, 2026
**Objetivo**: Dotar al `ResilienceManager` de inteligencia de correlación temporal (CorrelationEngine) y de capacidad de auto-reparación acotada (SelfHealingPlaybook). Exponer el estado del sistema inmunológico al operador humano vía API REST + WebSocket + `ResilienceConsole` UI, completando el ciclo inmunológico autónomo con supervisión humana.
**Épica**: E14 (EDGE Resilience Engine) | **Trace_ID**: EDGE-IGNITION-PHASE-5-SELF-HEALING / EDGE-IGNITION-PHASE-6-RESILIENCE-UI
**Dominios**: 10_INFRASTRUCTURE_RESILIENCY

## 📋 Tareas del Sprint

- [DONE] **HU 10.9: Stagnation Intelligence — Shadow con 0 operaciones** (Trace_ID: SHADOW-STAGNATION-INTEL-2026-04-05 | 2026-04-05)
  - `core_brain/operational_edge_monitor.py`: nuevo check `shadow_stagnation` integrado en `run_checks()` como 10° invariante OEM
  - Heurística de causa probable implementada: `OUTSIDE_SESSION_WINDOW` · `REGIME_MISMATCH` · `SYMBOL_NOT_WHITELISTED` · `UNKNOWN`
  - Idempotencia diaria por `instance_id` con persistencia en `sys_config` (`oem_shadow_stagnation_alerts_daily`) + cache en memoria del OEM
  - Registro de evidencia en `sys_audit_logs` vía `log_audit_event(action='SHADOW_STAGNATION_ALERT')`
  - Tests nuevos: `tests/test_oem_stagnation.py` (6/6 PASSED)
  - Compatibilidad OEM actualizada: tests de conteo de checks migrados de 9→10 en `test_operational_edge_monitor.py` y `test_oem_production_integration.py`
  - Validación focalizada: `53/53 PASSED` (OEM suite)
  - `scripts/validate_all.py`: `27/27 PASSED`
  - `start.py` validado en arranque (OEM levantado con `checks=10`; proceso detenido tras smoke test)

- [DONE] **HU 10.19: Hardening OEM + ADX + SSOT Naming** (Trace_ID: ETI-SRE-AUDIT-OEM-ADX-SSOT-2026-04-05 | 2026-04-05)
  - Heartbeat OEM endurecido con umbral configurable `oem_silenced_component_gap_seconds` y mensaje explícito de Componente Silenciado
  - Fail-fast ADX/OHLC aplicado en scanner + normalización robusta en integrity guard para evitar evaluación con dato inválido
  - Persistencia: tablas canónicas aditivas `sys_session_tokens` y `sys_position_metadata` con backfill desde legacy
  - Tests focalizados: 49/49 PASSED (`scanner`, `integrity_guard`, `oem`, `schema`, `system_db`)
  - `scripts/validate_all.py`: 27/27 PASSED
  - `start.py` validado en arranque (sin traceback de regresión; proceso detenido tras verificación)

- [DONE] **HU 10.18: DISC-003 — Descomposición de MainOrchestrator** (Trace_ID: DISC-003-2026-04-05 | 2026-04-05)
  - `core_brain/main_orchestrator.py` reducido a coordinador delgado con wrappers legacy para preservar patchability de tests
  - `core_brain/orchestrators/` creado con módulos `_init_methods`, `_lifecycle`, `_cycle_scan`, `_cycle_exec`, `_cycle_trade`, `_guard_suite`, `_background_tasks`, `_scan_methods`, `_discovery`, `_types`
  - Compatibilidad retroactiva restaurada para tests que parchean métodos/clases del módulo raíz (`psutil`, `StorageManager`, `SignalExpirationManager`, `broadcast_shadow_update`, wrappers `_init_*`, `_consume_oem_repair_flags`, `_check_and_run_weekly_shadow_evolution`, etc.)
  - Compatibilidad textual restaurada para `tests/test_strategy_registry_complete.py`, recuperando el baseline histórico completo
  - `pytest tests/ -q --tb=no --no-header` → `2269 passed, 3 skipped`
  - `scripts/validate_all.py` → `27/27 PASSED`
  - `start.py` validado sin traceback atribuible a DISC-003

- [DONE] **HU 9.4: Signal Review Queue — WS Push + Flow UI Contract Test** (Trace_ID: DISC-SIGNAL-REVIEW-WS-PUSH-2026-04-04 | 2026-04-04)
  - `ui/src/contexts/AethelgardContext.tsx`: bridge de evento `SIGNAL_REVIEW_PENDING` a bus interno `aethelgard:signal-review-pending`
  - `ui/src/hooks/useSignalReviews.ts`: consumo del evento push, inserción optimista y `refreshPending()` inmediato
  - Polling rebajado de 10s a 60s como fallback resiliente
  - `ui/src/__tests__/hooks/useSignalReviews.test.ts`: 3 tests de contrato (hook listener, fallback cadence, bridge context->hook)
  - `ui`: `npm run test -- src/__tests__/hooks/useSignalReviews.test.ts` ✅ 3/3 PASSED
  - `ui`: `npm run build` ✅ PASSED

- [DONE] **HU 10.17b: Veto Reasoner — Endpoint API + UI Component** (Trace_ID: EDGE-IGNITION-PHASE-6-RESILIENCE-UI | 2026-03-31)
  - `core_brain/api/routers/resilience.py` (NUEVO): `GET /api/v3/resilience/status` (postura, budget, exclusiones) + `POST /api/v3/resilience/command` (RETRY_HEALING, OVERRIDE_POSTURE, RELEASE_SCOPE)
  - `core_brain/server.py`: singleton `_resilience_manager_instance` + `set_resilience_manager()` / `get_resilience_manager()`
  - `core_brain/main_orchestrator.py`: `set_resilience_manager(self.resilience_manager)` publicado al servidor en el bloque #16
  - `core_brain/api/routers/telemetry.py`: `_get_resilience_status_snapshot()` inyectado en payload de `/ws/v3/synapse` → campo `resilience_status`
  - `ui/src/hooks/useSynapseTelemetry.ts`: interfaz `ResilienceSnapshot` + campo opcional `resilience_status` en `SynapseTelemetry`
  - `ui/src/components/diagnostic/ResilienceConsole.tsx` (NUEVO): badge de postura + narrativa dinámica + barra de presupuesto + tablas de exclusión + botones de intervención con spinners
  - `ui/src/components/diagnostic/MonitorPage.tsx`: `<ResilienceConsole />` integrado al final de la página
  - `tests/test_veto_reasoner.py`: 2 tests — endpoint 503 si manager no inicializado + serialización de postura/narrativa/exclusiones
  - `ui/src/__tests__/components/ResilienceConsole.test.ts`: 2 tests — contrato endpoint v3 + render narrativo condicional
  - `docs/10_INFRA_RESILIENCY.md`: sección "Manual Overrides" añadida (contrato de endpoints + UI)
  - Glassmorphism + bordes 0.5px + animaciones stagger 100ms (Dominio 09)

- [DONE] **HU 10.16: Self-Healing & Correlation Engine** (Trace_ID: ARCH-RESILIENCE-ENGINE-V1-C | 2026-03-31)
  - `core_brain/resilience_manager.py` actualizado con tres nuevos sub-sistemas:
    - **CorrelationEngine**: ventana deslizante de 60s; ≥3 activos distintos con MUTE → LOCKDOWN sintético → STRESSED. Evita re-trigger limpiando la ventana tras cascada.
    - **RootCauseDiagnosis**: acumula L1/QUARANTINE por DataProvider; ≥2 estrategias en mismo proveedor → upgrade a L2/SERVICE/SELF_HEAL → DEGRADED.
    - **SelfHealingPlaybook**: 3 recetas con max_retries=3 antes de escalar a STRESSED:
      - `Check_Data_Coherence` → `reconnect_provider_fn()` inyectado
      - `Check_Database` → `clear_db_cache_fn()` + `reconnect_provider_fn()` inyectados
      - `Spread_Anomaly` → cooldown de 300s (5 min) con `is_in_cooldown(scope)`
    - `is_healing: bool` property refleja si hay una curación en vuelo
    - Log format: `[AUTO-HEAL] [Attempt X/Y] Executing {action} for {scope}`
    - Callbacks inyectados al constructor (dependency inversion — no acoplamiento directo a infraestructura)
  - `tests/test_self_healing.py` (NUEVO): 27 tests — CorrelationEngine (5), RootCauseDiagnosis (4), HealDataCoherence (7), HealDatabase (4), SpreadAnomalyCooldown (4), IsHealingProperty (3)
  - Sin regresión: `test_resilience_manager.py` (27/27) + `test_resilience_interface.py` (23/23) = 50 tests previos verdes

- [DONE] **SRE Hotfix 2026-04-01 — ETI-CORE/PERSIST/GIT** (Trace_ID: SRE-AUDIT-2026-04-01T08:36 | 2026-04-01)
  - `ETI-GIT-001`: Commit de 7 artefactos untracked del ResilienceEngine (resilience.py, resilience_manager.py, api/routers/resilience.py, 3 test suites, ResilienceConsole.tsx) — commit `557c24a`
  - `ETI-CORE-001`: `strategy_monitor_service.py:155` — `get_all_usr_strategies()` (inexistente) → `get_all_sys_strategies()`. Mock de test actualizado. 21/21 tests verdes.
  - `ETI-PERSIST-001`: `data_vault/schema.py` — `DROP TABLE IF EXISTS edge_learning` añadido al final de `initialize_schema()` con guard `usr_edge_learning` (SSOT)
  - `ETI-PERSIST-002`: `main_orchestrator.py:_write_integrity_veto` — captura `sqlite3.IntegrityError` (duplicado → WARNING) separada de `sqlite3.OperationalError` (DB locked → ERROR). Import `sqlite3` añadido.
  - Commit: `59b078c`

## 📊 Snapshot de Cierre

- **HUs completadas**: 10.9 (Stagnation Intelligence), 10.19 (SRE Hardening), 10.18 (DISC-003 Orquestador), 10.17b (ResilienceConsole API+UI), 10.16 (Self-Healing+Correlation), 9.4 (Synapse WS Push), SRE-Hotfix-2026-04-01
- **Tests suite total**: 2269 passed, 3 skipped
- **validate_all.py**: 27/27 PASSED
- **Artefactos nuevos**: `core_brain/orchestrators/` (módulos de descomposición), `ui/src/components/diagnostic/ResilienceConsole.tsx`, `tests/test_schema_ssot_canonical_tables.py`, `tests/test_system_db_heartbeat_canonical.py`
- **Épicas completadas este sprint**: E13 (EDGE Reliability) + E14 (Resilience Engine) — ambas archivadas en SYSTEM_LEDGER
- **Deuda técnica**: tablas legacy `session_tokens` y `position_metadata` deprecación planificada (P2)

---

# SPRINT 24: EDGE RESILIENCE ENGINE — IMMUNE SYSTEM BRAIN — [DONE]

**Inicio**: 31 de Marzo, 2026
**Fin**: 31 de Marzo, 2026
**Objetivo**: Materializar el cerebro del sistema inmunológico: implementar `ResilienceManager` como árbitro único de la `SystemPosture`, refactorizar el `MainOrchestrator` para reemplazar el "Panic Button" de apagado por gestión de estado inteligente y resiliente, e implementar el Veto Reasoner para narrativa de estado en la UI.
**Épica**: E14 (EDGE Resilience Engine) | **Trace_ID**: EDGE-IGNITION-PHASE-4B-RESILIENCE-MANAGER
**Dominios**: 10_INFRASTRUCTURE_RESILIENCY

## 📋 Tareas del Sprint

- [DONE] **HU 10.15: ResilienceManager & Orchestrator Refactor** (Trace_ID: ARCH-RESILIENCE-ENGINE-V1-B | 2026-03-31)
  - `core_brain/resilience_manager.py` (NUEVO): clase `ResilienceManager` con `process_report(report) → SystemPosture`
  - Postura unidireccional (solo escala). Matriz de escalado: MUTE≥3→CAUTION, MUTE≥6→DEGRADED, QUARANTINE→CAUTION, SELF_HEAL→DEGRADED, LOCKDOWN→STRESSED
  - `core_brain/main_orchestrator.py` refactorizado:
    - Gate 1 (IntegrityGuard CRITICAL): ya no llama `_shutdown_requested = True`; reporta `L2/SELF_HEAL` al `ResilienceManager` → postura DEGRADED
    - Gate 2 (AnomalySentinel LOCKDOWN): ya no llama `_shutdown_requested = True`; reporta `L3/LOCKDOWN` → postura STRESSED
    - Check de postura al inicio del loop: solo STRESSED detiene el ciclo
    - Guard de postura DEGRADED en `run_single_cycle()`: bloquea SignalFactory/scan; PositionManager siempre ejecuta
  - `ResilienceManager` inicializado como `self.resilience_manager` (bloque #16 en `__init__`)
  - Criterios cumplidos: IntegrityGuard WARNING no detiene el loop; AnomalySentinel con 1 anomalía → CAUTION, no shutdown
  - `tests/test_resilience_manager.py`: 27 tests — escalado L0-L3, postura unidireccional, narrativa, persistencia audit

- [DONE] **HU 10.17: Veto Reasoner — Estado Narrativo en UI** (Trace_ID: ARCH-RESILIENCE-VETO-REASONER-V1 | 2026-03-31)
  - `ResilienceManager.get_current_status_narrative()`: retorna string legible con postura, scope, causa y plan de recuperación
  - `process_report()` incluye `recovery_plan` en `sys_audit_logs` (campo `details`: `reason | recovery_plan=...`)
  - Retorna `""` cuando postura NORMAL y sin reportes previos (no rompe la UI)
  - Cobertura de tests incluida en `tests/test_resilience_manager.py`
  - `docs/10_INFRA_RESILIENCY.md` §E14 actualizado con contrato real implementado

## 📊 Snapshot de Cierre

- **Tests añadidos**: 27 (`test_resilience_manager.py`) + 23 ya existentes (`test_resilience_interface.py`) = 50 tests E14
- **Archivos nuevos**: `core_brain/resilience_manager.py`, `tests/test_resilience_manager.py`
- **Archivos modificados**: `core_brain/main_orchestrator.py` (imports + init #16 + loop refactor + DEGRADED guard), `docs/10_INFRA_RESILIENCY.md` (§E14 contrato real)
- **Deuda eliminada**: "Panic Button" de apagado inmediato reemplazado por gestión de estado resiliente; Gates 1 y 2 ya no son disparadores de shutdown unilateral

---

# SPRINT 23: EDGE RELIABILITY — CERTEZA DE COMPONENTES & AUTO-AUDITORÍA — [DONE]

**Inicio**: 27 de Marzo, 2026
**Fin**: 31 de Marzo, 2026
**Objetivo**: Garantizar que el sistema se auto-audita en tiempo real mediante la activación del `OperationalEdgeMonitor` en producción, añadir guards de timeout en el loop principal para convertir bloqueos silenciosos en eventos observables, y establecer tests de contrato que conviertan cada bug conocido en una red de seguridad permanente contra regresiones.
**Épica**: E13 (EDGE Reliability) | **Trace_ID**: EDGE-RELIABILITY-SELF-AUDIT-2026
**Dominios**: 10_INFRASTRUCTURE_RESILIENCY

## 📋 Tareas del Sprint

- [DONE] **HU 10.10: OEM Production Integration**
  - `start.py`: `OperationalEdgeMonitor` instanciado con `shadow_storage` inyectado (línea ~543), thread daemon arranca después del SHADOW pool
  - `core_brain/server.py`: singleton `_oem_instance` + `set_oem_instance()` / `get_oem_instance()`
  - `core_brain/api/routers/system.py`: endpoint `GET /system/health/edge`
  - `ui/src/hooks/useOemHealth.ts`: hook HTTP polling cada 15 s
  - `ui/src/components/diagnostic/SystemHealthPanel.tsx`: panel UI con 9 check cards (componente + status + detalle)
  - `ui/src/components/diagnostic/MonitorPage.tsx`: `<SystemHealthPanel />` integrado al final de la página
  - `tests/test_oem_production_integration.py`: 9 tests — integración, singleton, endpoint UNAVAILABLE

- [DONE] **HU 10.11: OEM Loop Heartbeat Check**
  - `core_brain/operational_edge_monitor.py`: `_check_orchestrator_heartbeat()` como 9° check; `last_results` + `last_checked_at` en instancia; log de OK con warnings count; `CRITICAL` si heartbeat FAIL o >= 2 FAIL
  - Umbrales: `OK` < 10 min, `WARN` 10-20 min, `FAIL` > 20 min
  - `tests/test_oem_heartbeat_check.py`: 10 tests — OK/WARN/FAIL, umbrales exactos, integración con health_summary

- [DONE] **Batch A/B — DB Lock Cascade & trace_id Uniqueness (scenario_backtester.py)** *(fuera de HU formal — bug crítico detectado en auditoría ciclo 1)*
  - `core_brain/scenario_backtester.py` `_persist_validation`: `conn` movido fuera del `try` + `conn.rollback()` en `except` + `finally: self.storage._close_conn(conn)` → elimina lock indefinido cuando UNIQUE constraint falla
  - `core_brain/scenario_backtester.py` `run_scenario_backtest`: `trace_id` migrado de `%H%M%S` a `%H%M%S_%f` (microsegundos) → elimina `UNIQUE constraint failed: sys_shadow_promotion_log.trace_id` en lotes rápidos
  - validate_all: 27/27 PASSED

- [DONE] **Batch C — Connection Leaks en BacktestOrchestrator + Log Engañoso (Trace_ID: EDGE-CONNLEAK-BACKTEST-ORC-2026-03-30)**
  - `core_brain/backtest_orchestrator.py` `_execute_backtest`: todo el bloque multi-TF envuelto en `try/finally: _close_conn(conn)` (conn línea ~267 nunca se cerraba)
  - `core_brain/backtest_orchestrator.py` `_update_strategy_scores`: `conn` fuera de `try` + `rollback()` en `except` + `finally: _close_conn(conn)`
  - `core_brain/backtest_orchestrator.py` `_load_backtest_strategies`: `conn` fuera de `try` + `finally: _close_conn(conn)`
  - `core_brain/backtest_orchestrator.py` `_load_strategy`: idem
  - `core_brain/main_orchestrator.py` `initialize_shadow_pool`: `failed_count` separado de `skipped_count` (antes mezclaba filtros de modo con excepciones reales); retorno y log actualizados con las tres claves: `created`, `skipped`, `failed`
  - `tests/test_backtest_conn_leak.py`: 8 tests — `_close_conn` invocado en path exitoso y en path de excepción para cada método
  - `tests/test_shadow_pool_log_accuracy.py`: 4 tests — `failed` cuenta solo excepciones, `skipped` solo filtros de modo
  - validate_all: 27/27 PASSED

- [DONE] **HU 10.14: Resilience Playbook & Interface Definition** (Trace_ID: ARCH-RESILIENCE-ENGINE-V1-A | 2026-03-31)
  - `core_brain/resilience.py` (NUEVO): enums `ResilienceLevel` (L0-L3), `EdgeAction` (4 acciones exactas), `SystemPosture` (4 valores: NORMAL/CAUTION/DEGRADED/STRESSED); dataclass `EdgeEventReport` con `trace_id` auto-generado; clase abstracta `ResilienceInterface` con `check_health() → Optional[EdgeEventReport]`
  - Solo contratos y modelos — sin lógica de orquestación
  - `tests/test_resilience_interface.py`: 23 tests — valores de enums, instanciación de EdgeEventReport, trace_id único, ABC enforcement
  - validate_all: todos los tests PASSED

- [DONE] **HU 10.12: Timeout Guards en run_single_cycle**
  - `core_brain/main_orchestrator.py`: `asyncio.wait_for()` en `_request_scan()` (120s), `_check_and_run_daily_backtest()` (300s), `position_manager.monitor_usr_positions()` (60s)
  - `shadow_manager.evaluate_all_instances()`: mover a `asyncio.to_thread()` con timeout 60s (elimina bloqueo síncrono del event loop)
  - Timeouts configurables: `sys_config` claves `phase_timeout_scan_s`, `phase_timeout_backtest_s`
  - `tests/test_orchestrator_timeout_guards.py`: mock que no retorna → verificar ciclo continúa y logea `[TIMEOUT]`

- [DONE] **EDGE-IGNITION-PHASE-3-COHERENCE-DRIFT-2026-03-30: CoherenceService — Gate 3 (Deriva Modelo vs. Realidad)**
  - **Objetivo**: Tercer y último gate en el loop principal del orquestador. Detecta deriva entre el modelo teórico y la realidad operativa por estrategia, aplicando cuarentena selectiva sin detener el sistema.
  - `core_brain/services/coherence_service.py` — 3 nuevos métodos:
    - `calculate_slippage_monitor(symbol, n_trades=5)`: ratio `real_price / signal_price` sobre últimos 5 trades; alerta si slippage > 2 pips **o** desviación de precio > 0.02%.
    - `calculate_profit_factor_drift(strategy_id)`: compara PF teórico (mejor `sys_shadow_instances.profit_factor`) vs. real (`sys_signal_ranking.profit_factor`); desviación > 30% → estado `COHERENCE_LOW`.
    - `check_coherence_veto(strategy_id, symbol=None)`: **Veto_Method** (Dominio 06, HU 6.3); retorna `True` si `coherence_score < 0.60` **o** si PF drift > 30% AND score < 0.70. Fail-open en caso de error (no bloquea trading).
  - `core_brain/main_orchestrator.py` — integración EDGE-IGNITION-PHASE-3:
    - Import `CoherenceService`; instancia como `self.coherence_service = CoherenceService(storage=self.storage)` (bloque #15 en `__init__`).
    - **Coherence Gate** en el `while` del loop principal, como 3er check tras INTEGRITY y ANOMALY, antes de `run_single_cycle()`.
    - `_run_coherence_gate()`: itera `get_strategies_by_mode('LIVE')`; evalúa cada estrategia con `check_coherence_veto()`; cuarentena la afectada sin detener el orquestador.
    - `_write_coherence_veto(strategy_id, trace_id)`: persiste `action=COHERENCE_VETO` en `sys_audit_logs`; `UPDATE sys_shadow_instances SET status='QUARANTINED'`; actualiza `sys_signal_ranking.execution_mode='QUARANTINE'`.
  - **Protocolo diferencial**: Gates 1 y 2 detienen el orquestador (`_shutdown_requested=True`). Gate 3 cuarentena **por estrategia** — otras estrategias sanas continúan operando.
  - TDD: `tests/test_coherence_service.py` — 14/14 PASSED (existentes, sin regresión). `validate_all.py`: **27/27 PASSED**.
  - Trace_ID: EDGE-IGNITION-PHASE-3-COHERENCE-DRIFT

- [DONE] **FIX-MONITOR-SNAPSHOT-2026-03-30: Higiene Observabilidad — monitor_snapshot.py**
  - `scripts/monitor_snapshot.py`: (1) `encoding='utf-8', errors='replace'` en `open()` → elimina `UnicodeDecodeError` silencioso. (2) Query `sys_state` obsoleta → `SELECT key, value, updated_at FROM sys_config ORDER BY updated_at DESC LIMIT 10` (SSOT v2.x). Linter amplió el script con `check_file_mass_limits()` y `get_db_snapshot()` defensivo.
  - TDD: `tests/test_monitor_snapshot.py` — 9 tests (9/9 PASSED). Cubre: DB ausente, tabla sys_config, ausencia de sys_state, encoding UTF-8, bytes inválidos, JSON válido.
  - `validate_all.py`: 27/27 PASSED.

- [DONE] **FIX-BACKTEST-QUALITY-ZERO-SCORE-2026-03-30: Corrección score_shadow + metrics refresh en evaluate_all_instances (§7 Feedback Loop)**
  - **Problema**: `evaluate_all_instances()` usaba `instance.metrics` (cache de `sys_shadow_instances`, 0 desde creación). `calculate_instance_metrics_from_sys_trades()` existía pero **nunca se invocaba** en el ciclo de evaluación. Además `score_shadow` en `sys_strategies` nunca se escribía en ningún code path → motor Darwiniano paralizado.
  - **Gap A**: [shadow_manager.py:544](../core_brain/shadow_manager.py) — `metrics = instance.metrics` sustituido por llamada a `calculate_instance_metrics_from_sys_trades()` antes de cada evaluación. `instance.metrics` actualizado para que `update_shadow_instance()` persista métricas reales.
  - **Gap B**: `score_shadow` en `sys_strategies` — nuevo `ShadowStorageManager.update_strategy_score_shadow(strategy_id, score)` en `shadow_db.py`. Llamado desde `evaluate_all_instances()` después de cada instancia. Fórmula: `win_rate × min(profit_factor / 3.0, 1.0)`.
  - **Trigger manual**: nuevo `ShadowManager.recalculate_all_shadow_scores() → {"recalculated": N, "skipped": M}`. Permite recalcular sin esperar el ciclo horario (útil post-migración de datos históricos).
  - **Confirmación ETI §3**: `calculate_instance_metrics_from_sys_trades()` recibe datos no vacíos post-fix SHADOW-SYNC-ZERO-TRADES — tests documentan ambos casos (con y sin instance_id).
  - TDD: `tests/test_shadow_manager_metrics_refresh.py` — 7 tests (7/7 PASSED). Cubre: refresh desde sys_trades, cache actualizado post-evaluación, score_shadow > 0 con trades reales, recalculate_all_shadow_scores, bug NULL documentado.
  - `validate_all.py`: **2119/2119 PASSED** · 0 regresiones.

- [DONE] **FIX-SHADOW-SYNC-ZERO-TRADES-2026-03-30: Corrección ciclo Darwiniano — instance_id NULL en sys_trades**
  - **Root cause (Vector A)**: `TradeClosureListener._save_trade_with_retry()` construía `trade_data` sin `instance_id`. `BrokerTradeClosedEvent` no tiene ese campo → `sys_trades.instance_id = NULL` → `calculate_instance_metrics_from_sys_trades(instance_id)` retornaba 0 filas → todas las instancias SHADOW con 0 trades → ciclo Darwiniano (3 Pilares) ciego.
  - **Root cause (Vector B)**: `_get_execution_mode()` hacía fallback a `LIVE` cuando `sys_signal_ranking` no tenía entrada → trades enrutados a `usr_trades` en lugar de `sys_trades`.
  - `core_brain/trade_closure_listener.py`: nuevo método `_resolve_shadow_context(signal_id) → (execution_mode, instance_id)` que resuelve ambos vectores: (1) consulta `sys_signal_ranking`; (2) si modo SHADOW, busca instancia activa en `sys_shadow_instances` por `strategy_id`; (3) si ranking ausente pero existe instancia SHADOW activa, **infiere SHADOW** en lugar de LIVE. Nuevo helper `_lookup_shadow_instance_id(strategy_id)`. `_get_execution_mode()` redirige a `_resolve_shadow_context()` para compatibilidad. `_save_trade_with_retry()` incluye ahora `instance_id` en `trade_data`.
  - Confirmado: `save_trade_result()` en `data_vault/trades_db.py` rutea SHADOW → `sys_trades` correctamente (sin cambios necesarios). ADX regression (Problem 2) confirmado resuelto desde sprint anterior.
  - TDD: `tests/test_trade_closure_listener_shadow_sync.py` — 5 tests (5/5 PASSED). Cubre: `instance_id` en `trade_data`, `execution_mode` correcto, fallback por instancia activa, métricas visibles post-fix, documentación del bug original.
  - `validate_all.py`: 27/27 PASSED.

- [DONE] **EDGE-IGNITION-PHASE-1-INTEGRITY-GUARD-2026-03-30: Servicio de autodiagnóstico en runtime (IntegrityGuard)**
  - **Objetivo**: Chequeos vivos data-driven en cada ciclo de trading; veto automático ante estado CRITICAL con trazabilidad completa.
  - `core_brain/services/integrity_guard.py` — NUEVO: clase `IntegrityGuard` con tres checks:
    - `Check_Database`: conectividad + legibilidad de `sys_config` (catch amplio, mide elapsed_ms)
    - `Check_Data_Coherence`: detección de congelamiento de tick (umbral 5 min, `last_market_tick_ts` en `sys_config`)
    - `Check_Veto_Logic`: ADX nulo/cero persistente — WARNING tras 1 ciclo, CRITICAL tras 3 consecutivos (`_adx_zero_streak`)
  - `HealthStatus` (OK/WARNING/CRITICAL), `CheckResult`, `HealthReport` como value objects; Trace_ID obligatorio en cada log.
  - `core_brain/main_orchestrator.py` — import de `IntegrityGuard, HealthStatus`; step 13 en `__init__`; **Integrity Gate** al inicio del `while` en `run()`: si `check_health()` → CRITICAL, llama `_write_integrity_veto()` y detiene el ciclo.
  - `_write_integrity_veto(trace_id, checks)`: persiste fallo en `sys_audit_logs` con `action=INTEGRITY_VETO`, `status=failure`, `reason` truncado a 1000 chars.
  - TDD: `tests/test_integrity_guard.py` — 22 tests (22/22 PASSED). Cubre todos los caminos de los 3 checks + agregación + nivel de log.
  - `validate_all.py`: **27/27 PASSED** · suite total **2143/2143 PASSED** · 0 regresiones.

- [DONE] **FIX-LIFECYCLE-COHERENCE-STALE-BACKTEST-2026-03-30: updated_at congelado en sys_shadow_instances (§7 Feedback Loop)**
  - **Root cause**: `ShadowStorageManager.update_shadow_instance()` persistía `db_dict["updated_at"]` — el timestamp original deserializado en `from_db_dict`. El UPDATE escribía el mismo valor ya existente → campo congelado desde la creación → motor Darwiniano no podía detectar actividad de vida en las 5 estrategias afectadas.
  - **Fix**: [shadow_db.py:151](../data_vault/shadow_db.py) — `updated_at = ?` reemplazado por `updated_at = CURRENT_TIMESTAMP`; el parámetro `db_dict["updated_at"]` eliminado del tuple de binding. SQLite estampa el momento real del UPDATE en cada ciclo de evaluación.
  - **Dependencias**: Fix dependiente de P2 (FIX-SHADOW-SYNC-ZERO-TRADES) y P4 (FIX-BACKTEST-QUALITY-ZERO-SCORE) — los trades deben estar vinculados a instance_id para que el ciclo de backtest invoque `update_shadow_instance()` con datos reales.
  - TDD: `tests/test_shadow_db_updated_at_refresh.py` — 2 tests (2/2 PASSED). Cubre: `evaluate_all_instances()` avanza `updated_at`; `update_shadow_instance()` directamente avanza `updated_at`.
  - `validate_all.py`: **2121/2121 PASSED** · 0 regresiones.

- [DONE] **HU 10.13: Contract Tests — Bugs Conocidos**
  - `tests/test_contracts_known_bugs.py`: 4 tests de contrato (ver HU 10.13 en BACKLOG)
    1. `pilar3_min_trades` dinámico: instancia con 8 trades → HEALTHY si DB dice min_trades=5
    2. `_degrade_strategy()` huérfano: verificar comportamiento real y alinear docstring con código
    3. Métricas SHADOW en WebSocket: `broadcast_shadow_update` contiene profit_factor/win_rate reales
    4. `calculate_weighted_score`: integrar en flujo o eliminar dead code
  - Cada test debe estar RED antes del fix correspondiente, GREEN después

---

# SPRINT 22: SYS_TRADES — SEPARACIÓN EJECUCIÓN SISTEMA vs TENANT — [DONE]

**Inicio**: 26 de Marzo, 2026
**Fin**: 26 de Marzo, 2026
**Objetivo**: Crear tabla `sys_trades` (Capa 0 Global) exclusiva para trades SHADOW y BACKTEST, separándolos de `usr_trades` (Capa 1 Tenant, LIVE únicamente). Garantizar que el motor Darwiniano de SHADOW y el motor de backtesting escriban en `sys_trades` y que ningún análisis de rendimiento del trader sea contaminado con resultados de paper trades. Blindar `usr_trades` con TRIGGER a nivel de motor SQLite.
**Épica**: E8 (DATA_SOVEREIGNTY) | **Trace_ID**: EXEC-V8-SYS-TRADES-SEPARATION
**Dominios**: 08_DATA_SOVEREIGNTY · 07_ADAPTIVE_LEARNING

## 📋 Tareas del Sprint

- [DONE] **HU 8.1: sys_trades — Tabla de Ejecución del Sistema**
  - `data_vault/schema.py`: nueva tabla `sys_trades` (Capa 0) con `instance_id` (FK `sys_shadow_instances`), `account_id` (FK `sys_broker_accounts`), `execution_mode CHECK('SHADOW','BACKTEST')`, `strategy_id`, `direction`, `open_time`, `close_time`, `profit`, `order_id`; 4 índices; TRIGGER `trg_usr_trades_live_only` que bloquea cualquier INSERT no-LIVE en `usr_trades` a nivel de motor SQLite
  - `data_vault/trades_db.py`: `save_sys_trade()` (ValueError si LIVE), `get_sys_trades()` (filtros: mode/instance_id/strategy_id), `calculate_sys_trades_metrics()`; `save_trade_result()` rutea automáticamente SHADOW/BACKTEST → `sys_trades`
  - `data_vault/shadow_db.py`: `calculate_instance_metrics_from_sys_trades(instance_id)` — calcula `ShadowMetrics` completo (win_rate, profit_factor, equity_curve_cv, consecutive_losses_max) desde trades reales
  - `tests/test_shadow_schema.py`: clase `TestSysTradesSchema` (6 tests: existencia, columnas, CHECK, LIVE bloqueado, trigger, índices)
  - `tests/test_sys_trades_db.py` (nuevo): 13 tests — save/get/metrics, separación física vs `usr_trades`, doble enforcement app+DB
  - `docs/08_DATA_SOVEREIGNTY.md`: `sys_trades` en tabla Capa 0 + regla ARCH-SSOT-2026-007 con flujo Darwiniano completo
  - Corrección de 2 tests regresivos que esperaban SHADOW en `usr_trades` (comportamiento anterior)

## 📊 Snapshot de Cierre

- **Tests añadidos**: 19 (6 schema + 13 sys_trades_db)
- **Tests corregidos**: 2 (tests de comportamiento anterior)
- **Tests totales suite**: 1988/1988 PASSED (2 pre-existentes en `test_orchestrator_recovery.py` — bug timezone independiente, pendiente HU separada)
- **Archivos nuevos**: `tests/test_sys_trades_db.py`
- **Archivos modificados**: `data_vault/schema.py`, `data_vault/trades_db.py`, `data_vault/shadow_db.py`, `tests/test_shadow_schema.py`, `tests/test_fase_d_trades_migration.py`, `tests/test_fase_e_shadow_signal_persistence.py`, `docs/08_DATA_SOVEREIGNTY.md`
- **Garantía de aislamiento**: doble capa — ValueError en aplicación + TRIGGER en SQLite motor
- **Motor Darwiniano desbloqueado**: SHADOW → cuenta DEMO real → `sys_trades` → 3 Pilares → promote/kill

---

# SPRINT 21: DYNAMIC AGGRESSION ENGINE — S-9 — [DONE]

**Inicio**: 26 de Marzo, 2026
**Fin**: 26 de Marzo, 2026
**Objetivo**: Liberar agresividad del motor de señales de forma controlada: escalar el bonus de confluencia de forma proporcional a la confianza, desacoplar el filtro Trifecta mediante bandera por estrategia, e implementar el DynamicThresholdController para ajuste automático del umbral mínimo de confianza según sequía de señales y drawdown.
**Épica**: E12 | **Trace_ID**: EXEC-V7-DYNAMIC-AGGRESSION-ENGINE
**Dominios**: 03_ALPHA_ENGINE · 07_ADAPTIVE_LEARNING

## 📋 Tareas del Sprint

- [DONE] **HU 3.4: Confluencia Proporcional y Trifecta Asimétrica**
  - `core_brain/confluence.py`: `_scale_bonus_by_confidence()` — tres tiers: `<0.40→0.0x`, `[0.40,0.50]→0.5x`, `>0.50→1.0x`; metadata enriquecida con `confluence_bonus`, `confluence_scale_factor`, `confluence_bonus_raw`
  - `core_brain/signal_trifecta_optimizer.py`: reemplaza hardcode `strategy_id == 'oliver'` por flag `requires_trifecta` en `signal.metadata` (retro-compatible con estrategias Oliver)
  - `tests/test_confluence_proportional.py`: 9 tests (límites de tier, metadata, fluency test S-9, asymmetry test)
  - `docs/03_ALPHA_ENGINE.md`: sección HU 3.4/3.6 con tabla de tiers y comportamiento asimétrico

- [DONE] **HU 7.5: DynamicThresholdController — Motor de Exploración Activa**
  - `core_brain/adaptive/__init__.py` + `core_brain/adaptive/threshold_controller.py`: clase `DynamicThresholdController` con DI de `storage_conn`
  - Detección de sequía: ventana de 24h sobre `sys_signals` (modos SHADOW/BACKTEST); reduce `dynamic_min_confidence` −5% si sin señales (floor 0.40)
  - Feedback de drawdown: si `drawdown > 10%` → recupera umbral hacia base
  - Persiste en `sys_shadow_instances.parameter_overrides['dynamic_min_confidence']` como JSON
  - Solo actúa sobre instancias `INCUBATING` / `SHADOW_READY`
  - Trace_ID: `TRACE_DTC_{YYYYMMDD}_{HHMMSS}_{instance_id[:8].upper()}`
  - `tests/test_dynamic_threshold_controller.py`: 12 tests (sequía, drawdown, floor, casos especiales)
  - `docs/07_ADAPTIVE_LEARNING.md`: sección DTC con flujo, tabla de feedback y límites de gobernanza
  - `governance/BACKLOG.md`: HU 7.5 y HU 3.4 añadidas como `[DONE]`

- [DONE] **Bugfixes pre-existentes (sin HU asignada)**
  - `tests/test_backtest_multipair_sequential.py`: `_make_conn()` faltaba tabla `sys_strategy_pair_coverage` → 3 tests FAILED corregidos
  - `tests/test_ctrader_connector.py`: `_session_last_used_at` no inicializado en test → idle-timeout falso positivo corregido
  - `tests/test_orchestrator.py` + `test_module_toggles.py` + `test_orchestrator_recovery.py` + `test_strategy_gatekeeper_wiring.py`: `_check_and_run_daily_backtest` sin parchear → llamadas HTTP reales colgaban ~250s/test → fixture `autouse=True` con `AsyncMock`
  - `tests/test_provider_cache.py`: `GenericDataProvider.fetch_ohlc` sin parchear → 18s/test → fixture `autouse=True`

## 📊 Snapshot de Cierre

- **Tests añadidos**: 21 (9 confluencia + 12 DTC)
- **Tests totales suite completa**: 1973/1973 PASSED
- **Tiempo de ejecución suite**: 96s (antes: 880s+ / colgaba indefinidamente)
- **Archivos nuevos**: `core_brain/adaptive/__init__.py`, `core_brain/adaptive/threshold_controller.py`, `tests/test_confluence_proportional.py`, `tests/test_dynamic_threshold_controller.py`
- **Archivos modificados**: `core_brain/confluence.py`, `core_brain/signal_trifecta_optimizer.py`, `docs/03_ALPHA_ENGINE.md`, `docs/07_ADAPTIVE_LEARNING.md`, `governance/BACKLOG.md`, + 5 test files (bugfixes)
- **HUs completadas**: HU 3.4, HU 7.5
- **Bugs corregidos (pre-existentes)**: 4

---

# SPRINT 20: ALPHA HUNTER — MOTOR AUTÓNOMO DE MUTACIÓN — [DONE]

**Inicio**: 26 de Marzo, 2026
**Fin**: 26 de Marzo, 2026
**Objetivo**: Implementar `AlphaHunter` como motor autónomo de generación de variantes: clonar estrategias, variar `parameter_overrides` con distribución normal, y promover automáticamente al pool SHADOW las variantes que superen `overall_score > 0.85`, con límite de 20 instancias activas.
**Épica**: E11 | **Trace_ID**: EXEC-V6-ALPHA-HUNTER-GEN-2026-03-26
**Dominios**: 07_ADAPTIVE_LEARNING

## 📋 Tareas del Sprint

- [DONE] **HU 7.20: AlphaHunter — Motor de Mutación y Auto-Promoción**
  - `core_brain/alpha_hunter.py`: clase `AlphaHunter` con DI de `storage_conn`
  - `mutate_parameters()`: aplica `N(μ=valor, σ=|valor|×0.05)` a parámetros numéricos; no-numéricos copiados sin modificar; bounds: `max(0.0, noisy)`
  - `try_promote_mutant()`: evalúa `overall_score > 0.85` (estricto) + `count_active < 20`; si pasan → INSERT en `sys_shadow_instances` con `status='INCUBATING'`, `account_type='DEMO'`, `backtest_score`, `backtest_trace_id`
  - `count_active_shadow_instances()`: excluye `DEAD` y `PROMOTED_TO_REAL`
  - `generate_mutation_trace_id()`: patrón `TRACE_ALPHAHUNTER_{YYYYMMDD}_{HHMMSS}_{strategy_id[:8].upper()}`
  - `docs/07_ADAPTIVE_LEARNING.md`: nueva sección "Generación Autónoma de Alfas"

## 📊 Snapshot de Cierre

- **Tests añadidos**: 19
- **Tests totales (módulo)**: 19/19 PASSED
- **Archivos nuevos**: `core_brain/alpha_hunter.py`, `tests/test_alpha_hunter.py`
- **Archivos modificados**: `docs/07_ADAPTIVE_LEARNING.md`
- **HUs completadas**: HU 7.20
- **Épica E11**: ✅ COMPLETADA — archivada en SYSTEM_LEDGER

---

# SPRINT 19: BACKTEST ENGINE — OVERFITTING DETECTOR — [DONE]

**Inicio**: 25 de Marzo, 2026
**Fin**: 25 de Marzo, 2026
**Objetivo**: Detectar riesgo de overfitting cuando >80% de los pares evaluados superan `effective_score >= 0.90` con `confidence >= 0.70`, marcando el flag en `AptitudeMatrix`, registrando alerta en `sys_audit_logs` y propagando `overfitting_risk` al resultado de `_execute_backtest()`.
**Épica**: E10 | **Trace_ID**: EDGE-BKT-719-OVERFITTING-DETECTOR-2026-03-24
**Dominios**: 07_ADAPTIVE_LEARNING

## 📋 Tareas del Sprint

- [DONE] **HU 7.19: Detector de overfitting por par**
  - `AptitudeMatrix.overfitting_risk: bool = False` añadido al dataclass + serializado en `to_json()`
  - `BacktestOrchestrator._detect_overfitting_risk()`: cuenta pares con `eff >= 0.90` AND `confidence = n/(n+k) >= 0.70`; activa si `n_flagged/n_total > 0.80` con al menos 2 pares
  - `BacktestOrchestrator._write_overfitting_alert()`: INSERT en `sys_audit_logs` con `action='OVERFITTING_RISK_DETECTED'` y payload JSON con n_pairs/n_flagged
  - `_execute_backtest()`: llama `_detect_overfitting_risk()` tras loop multi-par; si True → `_write_overfitting_alert()` + propaga flag en matriz representativa
  - No bloquea promoción automática

## 📊 Snapshot de Cierre

- **Tests añadidos**: 13
- **Tests totales (módulos afectados)**: 143/143 PASSED · validate_all 27/27
- **Archivos nuevos**: `tests/test_backtest_overfitting_detector.py`
- **Archivos modificados**: `core_brain/scenario_backtester.py`, `core_brain/backtest_orchestrator.py`
- **HUs completadas**: HU 7.19
- **Épica E10**: ✅ COMPLETADA — todas las HUs archivadas

---

# SPRINT 18: BACKTEST ENGINE — BACKTEST PRIORITY QUEUE — [DONE]

**Inicio**: 25 de Marzo, 2026
**Fin**: 25 de Marzo, 2026
**Objetivo**: Implementar `BacktestPriorityQueue` — componente que determina qué combinación `(strategy_id, symbol, timeframe)` evaluar en cada slot, ordenada por 6 tiers de prioridad usando `sys_strategy_pair_coverage` e integrada con `OperationalModeManager` para escalar el presupuesto según contexto operacional.
**Épica**: E10 | **Trace_ID**: EDGE-BKT-718-SMART-SCHEDULER-2026-03-24
**Dominios**: 07_ADAPTIVE_LEARNING

## 📋 Tareas del Sprint

- [DONE] **HU 7.18: Scheduler inteligente de backtests — prioritized queue**
  - `BacktestPriorityQueue` en `core_brain/backtest_orchestrator.py`
  - `get_max_slots()`: AGGRESSIVE=10 · MODERATE=5 · CONSERVATIVE=2 · DEFERRED=0 (integra `OperationalModeManager`)
  - `get_queue()`: retorna lista de `{strategy_id, symbol, timeframe}` ordenados por tier, capped a `max_slots`
  - `_priority_tier(coverage_row, ...)`: tiers 1-7 según status/n_cycles/effective_score del coverage
  - Tiers: P1(sin cobertura) → P2(PENDING n≤1) → P3(PENDING n>1) → P4(QUALIFIED n<3) → P5(baja confianza) → P6(QUALIFIED estable) → P7(REJECTED)
  - `_load_coverage()`: lookup en `sys_strategy_pair_coverage` por (strategy_id, symbol, timeframe)
  - LIVE_ACTIVE → BacktestBudget.CONSERVATIVE → 2 slots (reduce presupuesto CPU)

## 📊 Snapshot de Cierre

- **Tests añadidos**: 19
- **Tests totales (módulos afectados)**: 130/130 PASSED · validate_all 27/27
- **Archivos nuevos**: `tests/test_backtest_priority_queue.py`
- **Archivos modificados**: `core_brain/backtest_orchestrator.py`
- **HUs completadas**: HU 7.18
- **Desbloqueadas para siguiente sprint**: HU 7.19 (Detector de overfitting)

---

# SPRINT 17: BACKTEST ENGINE — STRATEGY PAIR COVERAGE TABLE — [DONE]

**Inicio**: 25 de Marzo, 2026
**Fin**: 25 de Marzo, 2026
**Objetivo**: Crear la tabla `sys_strategy_pair_coverage` para rastrear cobertura empírica por (estrategia, símbolo, timeframe, régimen) e integrar su escritura en `BacktestOrchestrator` al completar cada evaluación de par.
**Épica**: E10 | **Trace_ID**: EDGE-BKT-717-COVERAGE-TABLE-2026-03-24
**Dominios**: 07_ADAPTIVE_LEARNING, 08_DATA_SOVEREIGNTY

## 📋 Tareas del Sprint

- [DONE] **HU 7.17: Tabla sys_strategy_pair_coverage**
  - DDL en `initialize_schema()`: tabla con 11 columnas, UNIQUE(strategy_id, symbol, timeframe, regime), índices en strategy_id y status
  - `BacktestOrchestrator._write_pair_coverage()`: UPSERT que incrementa `n_cycles` en conflicto y actualiza score/status/timestamp
  - `BacktestOrchestrator._get_current_regime_label()`: helper que retorna el régimen detectado (reusa required_regime para estrategias no-ANY; detecta régimen real para ANY)
  - `_execute_backtest()` llama a `_write_pair_coverage()` al finalizar cada par (Step 5, tras `_write_pair_affinity`)
  - Migration idempotente: `CREATE TABLE IF NOT EXISTS` + idxs `IF NOT EXISTS`

## 📊 Snapshot de Cierre

- **Tests añadidos**: 11
- **Tests totales (módulos afectados)**: 111/111 PASSED · validate_all 27/27
- **Archivos nuevos**: `tests/test_strategy_pair_coverage_table.py`
- **Archivos modificados**: `data_vault/schema.py`, `core_brain/backtest_orchestrator.py`
- **HUs completadas**: HU 7.17
- **Desbloqueadas para siguiente sprint**: HU 7.18 (Scheduler inteligente)

---

# SPRINT 16: BACKTEST ENGINE — REGIME COMPATIBILITY FILTER — [DONE]

**Inicio**: 25 de Marzo, 2026
**Fin**: 25 de Marzo, 2026
**Objetivo**: Formalizar y cubrir con tests explícitos el filtro de compatibilidad de régimen pre-evaluación: estrategias con `required_regime='TREND'` no procesan pares en RANGE; pares incompatibles quedan marcados `REGIME_INCOMPATIBLE` con timestamp; estrategias con `required_regime='ANY'` no aplican el filtro.
**Épica**: E10 | **Trace_ID**: EDGE-BKT-716-REGIME-FILTER-2026-03-24
**Dominios**: 07_ADAPTIVE_LEARNING

## 📋 Tareas del Sprint

- [DONE] **HU 7.16: Filtro de compatibilidad de régimen pre-evaluación**
  - Comportamiento ya implementado en HU 7.9 (`_passes_regime_prefilter()`) y HU 7.14 (`_write_regime_incompatible()`, loop multi-par)
  - 14 tests explícitos en `tests/test_backtest_regime_compatibility_filter.py` cubriendo los 3 AC de la HU
  - AC1: `required_regime='TREND'` → False cuando detected=RANGE
  - AC2: `_write_regime_incompatible()` persiste `REGIME_INCOMPATIBLE` + `last_updated` timestamp + preserva datos históricos
  - AC3: `required_regime='ANY'` siempre retorna True (y `None` / campo ausente tratado como ANY)
  - Casos adicionales: alias `TRENDING→TREND`, fail-open con <14 bars o sin datos, sin efectos en otros símbolos

## 📊 Snapshot de Cierre

- **Tests añadidos**: 14
- **Tests totales (módulos afectados)**: 100/100 PASSED · validate_all 27/27
- **Archivos nuevos**: `tests/test_backtest_regime_compatibility_filter.py`
- **Archivos modificados**: ninguno (implementación pre-existente)
- **HUs completadas**: HU 7.16
- **Desbloqueadas para siguiente sprint**: HU 7.17, HU 7.18

---

# SPRINT 15: BACKTEST ENGINE — STATISTICAL CONFIDENCE SCORING — [DONE]

**Inicio**: 25 de Marzo, 2026
**Fin**: 25 de Marzo, 2026
**Objetivo**: Implementar la fórmula de confianza estadística continua `n/(n+k)` para penalizar scores de estrategias con pocos trades, eliminando el placeholder `confidence=1.0` de HU 7.13.
**Épica**: E10 | **Trace_ID**: EDGE-BKT-715-CONFIDENCE-SCORING-2026-03-24
**Dominios**: 07_ADAPTIVE_LEARNING

## 📋 Tareas del Sprint

- [DONE] **HU 7.15: Score con confianza estadística n/(n+k)**
  - Nueva función pública `compute_confidence(n_trades, k)` en `backtest_orchestrator.py`
  - `_write_pair_affinity()` actualizado: lee `confidence_k` de `execution_params` (fallback a `sys_config`, default 20), calcula `confidence = n/(n+k)`, `effective_score = raw_score × confidence`
  - Lógica de status revisada:
    - `effective_score >= 0.55` → QUALIFIED
    - `effective_score < 0.20 AND confidence >= 0.50` → REJECTED (guard prevents premature rejection)
    - otherwise → PENDING
  - `_load_config()`: añade `"confidence_k": 20` a defaults
  - TDD: 17 tests en `tests/test_backtest_confidence_scoring.py` — 17/17 PASSED

## 📊 Snapshot de Cierre

- **Tests añadidos**: 17
- **Tests totales (módulos afectados)**: 86/86 PASSED · validate_all 27/27
- **Archivos nuevos**: `tests/test_backtest_confidence_scoring.py`
- **Archivos modificados**: `core_brain/backtest_orchestrator.py`
- **HUs completadas**: HU 7.15
- **Desbloqueadas para siguiente sprint**: HU 7.16, HU 7.17

---

# SPRINT 14: BACKTEST ENGINE — MULTI-PAIR SEQUENTIAL EVALUATION — [DONE]

**Inicio**: 25 de Marzo, 2026
**Fin**: 25 de Marzo, 2026
**Objetivo**: Extender `_execute_backtest()` para evaluar todos los símbolos del `market_whitelist` de forma secuencial, escribiendo una entrada en `affinity_scores` por par evaluado y registrando `REGIME_INCOMPATIBLE` para pares vetados por el pre-filtro de régimen.
**Épica**: E10 | **Trace_ID**: EDGE-BKT-714-MULTI-PAIR-2026-03-24
**Dominios**: 07_ADAPTIVE_LEARNING

## 📋 Tareas del Sprint

- [DONE] **HU 7.14: Backtesting multi-par secuencial**
  - Nuevo `BacktestOrchestrator._get_symbols_for_backtest(strategy)`: lee `market_whitelist`, normaliza "EUR/USD"→"EURUSD", fallback a `default_symbol`
  - `BacktestOrchestrator._build_scenario_slices()`: parámetro `symbol` opcional para iterar pares sin depender de `_resolve_symbol_timeframe()`
  - Round-robin key cambiado a `strategy_id:symbol` para rotación independiente por par
  - `_execute_backtest()` rediseñado: loop secuencial sobre símbolos → pre-filtro régimen por par → backtester → `_write_pair_affinity()` por par → score agregado (media)
  - Nuevo `_write_regime_incompatible(cursor, strategy_id, symbol, strategy)`: escribe `{status: REGIME_INCOMPATIBLE, last_updated}` preservando datos históricos del par
  - `run_pending_strategies()`: `asyncio.gather()` reemplazado por loop secuencial (seguridad DB — evita write collisions)
  - `tests/test_backtest_orchestrator.py`: `mock_backtester.MIN_REGIME_SCORE = 0.75` añadido al helper
  - TDD: 11 tests en `tests/test_backtest_multipair_sequential.py` — 11/11 PASSED

## 📊 Snapshot de Cierre

- **Tests añadidos**: 11
- **Tests totales (módulos afectados)**: 122/122 PASSED · validate_all 27/27
- **Archivos nuevos**: `tests/test_backtest_multipair_sequential.py`
- **Archivos modificados**: `core_brain/backtest_orchestrator.py`, `tests/test_backtest_orchestrator.py`
- **HUs completadas**: HU 7.14
- **Desbloqueadas para siguiente sprint**: HU 7.15 (confianza n/(n+k))

---

# SPRINT 13: BACKTEST ENGINE — AFFINITY SCORES SEMANTIC REDESIGN — [DONE]

**Inicio**: 25 de Marzo, 2026
**Fin**: 25 de Marzo, 2026
**Objetivo**: Corregir el bug semántico de `affinity_scores` (usaba opiniones del desarrollador como parámetros operativos) y redefinirlo como output exclusivo del proceso de evaluación empírica por par.
**Épica**: E10 | **Trace_ID**: EDGE-BKT-713-AFFINITY-REDESIGN-2026-03-24
**Dominios**: 07_ADAPTIVE_LEARNING

## 📋 Tareas del Sprint

- [DONE] **HU 7.13: Rediseño semántico de affinity_scores**
  - `BacktestOrchestrator._extract_parameter_overrides()`: corregido para leer `execution_params` (no `affinity_scores`)
  - SELECT queries en `_load_backtest_strategies()` y `_load_strategy()`: añaden `execution_params`
  - `BacktestOrchestrator._update_strategy_scores()`: firma ampliada con `symbol` y `matrix` opcionales
  - Nuevo método `BacktestOrchestrator._write_pair_affinity()`: escribe estructura semántica por par con 12 campos: `effective_score, raw_score, confidence, n_trades, profit_factor, max_drawdown, win_rate, optimal_timeframe, regime_evaluated, status, cycles, last_updated`
  - Lógica de status: `QUALIFIED` (≥0.55) · `REJECTED` (<0.20) · `PENDING` (0.20–0.54)
  - `_execute_backtest()`: extrae `symbol` y pasa `matrix` a `_update_strategy_scores()`
  - `data_vault/schema.py`: migración `run_migrations()` resetea `affinity_scores = '{}'` para estrategias con contenido legacy (valores numéricos top-level)
  - TDD: 15 tests en `tests/test_backtest_affinity_redesign.py` — 15/15 PASSED

## 📊 Snapshot de Cierre

- **Tests añadidos**: 15
- **Tests totales (módulos afectados)**: 15/15 PASSED
- **Archivos nuevos**: `tests/test_backtest_affinity_redesign.py`
- **Archivos modificados**: `core_brain/backtest_orchestrator.py`, `data_vault/schema.py`
- **HUs completadas**: HU 7.13
- **Desbloqueadas para siguiente sprint**: HU 7.14, HU 7.15, HU 7.16 (paralelo a 7.14)

---

# SPRINT 12: BACKTEST ENGINE — MULTI-TIMEFRAME, REGIME CLASSIFIER & ADAPTIVE SCHEDULER — [DONE]

**Inicio**: 25 de Marzo, 2026
**Fin**: 25 de Marzo, 2026
**Objetivo**: Completar las HUs desbloqueadas de E10: incorporar evaluación multi-timeframe con round-robin y pre-filtro de régimen, integrar el RegimeClassifier real (ADX/ATR/SMA) en el pipeline de clasificación de ventanas, y crear el AdaptiveBacktestScheduler con cooldown dinámico y cola de prioridad.
**Épica**: E10 | **Trace_ID**: EDGE-BACKTEST-SPRINT12-MULTITF-REGIME-SCHED-2026-03-25
**Dominios**: 07_ADAPTIVE_LEARNING

## 📋 Tareas del Sprint

- [DONE] **HU 7.9: Evaluación multi-timeframe con round-robin y pre-filtro de régimen**
  - `BacktestOrchestrator._get_timeframes_for_backtest()`: lee `required_timeframes` de la estrategia
  - `BacktestOrchestrator._next_timeframe_round_robin()`: rotación cíclica in-memory por strategy_id
  - `BacktestOrchestrator._passes_regime_prefilter()`: valida `required_regime` contra régimen actual (fail-open si sin datos)
  - `_build_scenario_slices()`: integra round-robin + pre-filtro antes del fetch de datos
  - Queries DB actualizadas: incluyen `required_timeframes, required_regime` en SELECT
  - TDD: 14 tests en `tests/test_backtest_multitimeframe_roundrobin.py` — 14/14 PASSED

- [DONE] **HU 7.10: RegimeClassifier real en pipeline de backtesting**
  - `REGIME_TO_CLUSTER` ampliado: añade `CRASH → HIGH_VOLATILITY` y `NORMAL → STAGNANT_RANGE`
  - `BacktestOrchestrator._classify_window_regime()`: usa `RegimeClassifier` (ADX/ATR/SMA) con fallback a heurística ATR
  - `_split_into_cluster_slices()`: sustituye `backtester._detect_regime()` por `_classify_window_regime()`
  - Import de `RegimeClassifier` en `backtest_orchestrator.py`
  - TDD: 14 tests en `tests/test_backtest_regime_classifier.py` — 14/14 PASSED

- [DONE] **HU 7.12: Adaptive Backtest Scheduler — cooldown dinámico y queue de prioridad**
  - Nuevo módulo `core_brain/adaptive_backtest_scheduler.py`
  - `get_effective_cooldown_hours()`: delega a `OperationalModeManager.get_component_frequencies()`
  - `is_deferred()`: retorna True si presupuesto es DEFERRED
  - `get_priority_queue()`: excluye en cooldown, ordena P1(nunca run) > P2(score=0) > P3(más antigua)
  - TDD: 14 tests en `tests/test_adaptive_backtest_scheduler.py` — 14/14 PASSED

## 📊 Snapshot de Cierre

- **Tests añadidos**: 42 (14 HU7.9 + 14 HU7.10 + 14 HU7.12)
- **Tests totales (módulos afectados)**: 126/126 PASSED
- **Archivos nuevos**: `core_brain/adaptive_backtest_scheduler.py`, `tests/test_backtest_multitimeframe_roundrobin.py`, `tests/test_backtest_regime_classifier.py`, `tests/test_adaptive_backtest_scheduler.py`
- **Archivos modificados**: `core_brain/backtest_orchestrator.py`
- **HUs completadas**: HU 7.9, HU 7.10, HU 7.12
- **Desbloqueadas para siguiente sprint**: HU 7.13 (requiere 7.9+7.10+7.12)

---

# SPRINT 11: PRODUCTION UNBLOCK — SYMBOL FORMAT, BACKTEST SEED & ADAPTIVE PILAR 3 — [DONE]

**Inicio**: 25 de Marzo, 2026
**Fin**: 25 de Marzo, 2026
**Objetivo**: Eliminar los 3 bloqueantes que impedían la generación de señales reales: formato de símbolo incorrecto en 3 estrategias, cooldown de backtest sin sembrar, y Pilar 3 con umbral fijo de 15 trades imposible de alcanzar en el corto plazo.
**Épica**: E10 (HUs de soporte) | **Trace_ID**: PROD-UNBLOCK-SIGNAL-FLOW-2026-03-25
**Dominios**: 03_ALPHA_GENERATION · 07_ADAPTIVE_LEARNING

## 📋 Tareas del Sprint

- [DONE] **N2-2: Symbol format normalization — AFFINITY_SCORES slash→no-slash en 3 estrategias**
  - `liq_sweep_0001.py`, `mom_bias_0001.py`, `struc_shift_0001.py`: claves `"EUR/USD"` → `"EURUSD"` (y similares)
  - Root cause: scanner produce `"EURUSD"`, estrategias buscaban `"EUR/USD"` → 0 señales
  - TDD: 10 tests en `tests/test_symbol_format_strategies.py` — 10/10 PASSED (confirmado RED antes del fix)
  - Tests actualizados: `tests/test_struc_shift_0001.py` — 14/14 PASSED

- [DONE] **HU 10.8: Backtest config seed — cooldown_hours=1 en sys_config**
  - `_seed_backtest_config(storage)` en `start.py` — idempotente, INSERT OR IGNORE semántico
  - Seeds `backtest_config` con `cooldown_hours=1` (antes: hardcoded 24h sin seed → bloqueaba ciclo backtest)
  - TDD: 4 tests en `tests/test_start_singleton.py::TestSeedBacktestConfig` — 4/4 PASSED

- [DONE] **HU 3.13: Pilar 3 adaptativo — umbral configurable via dynamic_params**
  - `PromotionValidator(min_trades=15)` — constructor acepta umbral configurable (antes: constante de clase)
  - `ShadowManager(pilar3_min_trades=5)` — lee `dynamic_params.pilar3_min_trades` en arranque
  - `_seed_risk_config()` actualizado: siembra `pilar3_min_trades=5` en `dynamic_params` (patch idempotente para instalaciones existentes)
  - `main_orchestrator.py`: `ShadowManager` recibe valor leído de DB en construcción
  - TDD: 4 tests nuevos en `tests/test_shadow_manager.py::TestPromotionValidator` — 22/22 PASSED total

## 📊 Snapshot de Cierre

- **Tests añadidos**: 18 (10 N2-2 + 4 HU10.8 + 4 HU3.13)
- **Tests totales ejecutados**: 22/22 `test_shadow_manager.py` · 41/41 `test_symbol_format + test_struc_shift + test_start_singleton`
- **Archivos modificados**: `core_brain/strategies/liq_sweep_0001.py`, `core_brain/strategies/mom_bias_0001.py`, `core_brain/strategies/struc_shift_0001.py`, `start.py`, `core_brain/shadow_manager.py`, `core_brain/main_orchestrator.py`, `tests/test_struc_shift_0001.py`, `tests/test_shadow_manager.py`, `tests/test_start_singleton.py`
- **Archivos nuevos**: `tests/test_symbol_format_strategies.py`
- **Deuda eliminada**: 0 señales de 3/6 estrategias por formato; cooldown 24h sin seed; Pilar 3 bloqueando shadow con < 15 trades

---

# SPRINT 10: PIPELINE FIXES — SSOT RISK SEED, INSTRUMENT-AWARE SL/TP & CTRADER SESSION — [DONE]

**Inicio**: 25 de Marzo, 2026
**Fin**: 25 de Marzo, 2026
**Objetivo**: Eliminar warnings operacionales persistentes, corregir cálculo de SL/TP para instrumentos no-forex, y resolver degradación recurrente de CTrader por rate-limiting de autenticaciones.
**Épica**: E10 (HUs de soporte) | **Trace_ID**: PIPELINE-OPS-FIXES-2026-03-25
**Dominios**: 03_ALPHA_GENERATION · 10_INFRASTRUCTURE_RESILIENCY

## 📋 Tareas del Sprint

- [DONE] **HU 3.10: Risk Manager — Seed de parámetros dinámicos en sys_config**
  - `_seed_risk_config(storage)` en `start.py` — INSERT OR IGNORE semántico
  - Seeds `risk_settings` y `dynamic_params` con defaults seguros antes de instanciar `RiskManager`
  - Idempotente: no sobreescribe valores modificados por usuario
  - Eliminado: `[SSOT] Risk/dynamic config not in DB` en arranque nominal
  - TDD: 4 tests en `tests/test_start_singleton.py` — 13/13 PASSED (incluye tests previos)

- [DONE] **HU 3.11: Buffers SL/TP dinámicos por tipo de instrumento en estrategias**
  - `SessionExtension0001Strategy._sl_buffer(symbol, price)` — método estático
  - Clasifica instrumento por patrón de nombre: FOREX=0.0005, JPY=0.05, METALS=0.50, INDEXES=5.0
  - `analyze()` consume el buffer dinámico — sin regresión en `evaluate_on_history()`
  - TDD: 13 tests en `tests/test_sess_ext_sl_buffer.py` — 13/13 PASSED

- [DONE] **N1-8: CTrader Session Persistence — WebSocket persistente entre fetches**
  - `_session_ws` + `_session_loop` en `__init__` para tracking de sesión activa
  - `_fetch_bars_via_websocket()` reusa sesión existente (solo pasos 3-4) o conecta+autentica si está muerta
  - `_authenticate_session(ws)` → pasos 1-2 (APP_AUTH + ACCOUNT_AUTH)
  - `_fetch_bars_on_session(ws, symbol, tf, count)` → pasos 3-4 (symbol resolve + trendbars)
  - `_invalidate_session()` → cierra y limpia la sesión ante errores
  - Auth reducida de O(N_símbolos × N_ciclos) a O(1_por_sesión) → elimina rate-limit 2142
  - TDD: 7 tests en `tests/test_ctrader_connector.py::TestCTraderSessionPersistence` — 47/47 PASSED (total)

## 📊 Snapshot de Cierre

- **Tests añadidos**: 24 (4 HU3.10 + 13 HU3.11 + 7 N1-8)
- **Tests totales ejecutados**: 47/47 `test_ctrader_connector.py` + 26/26 `test_start_singleton.py` + `test_sess_ext_sl_buffer.py`
- **Archivos modificados**: `start.py`, `core_brain/strategies/session_extension_0001.py`, `connectors/ctrader_connector.py`, `tests/test_ctrader_connector.py`, `governance/BACKLOG.md`
- **Archivos nuevos**: `tests/test_sess_ext_sl_buffer.py`
- **Deuda eliminada**: warning SSOT en cada arranque; buffer forex inválido para índices; auth storm recurrente de CTrader

---

# SPRINT 9: MOTOR DE BACKTESTING INTELIGENTE — EDGE EVALUATION FRAMEWORK — [DONE]

**Inicio**: 24 de Marzo, 2026
**Fin**: 24 de Marzo, 2026
**Objetivo**: Refundar el motor de backtesting: reemplazar la simulación momentum genérica con lógica real por estrategia, eliminar la síntesis de datos en producción, agregar contexto estructural (régimen/timeframe) a sys_strategies, e implementar el gestor adaptativo de recursos operacionales.
**Épica**: E10 | **Trace_ID**: EDGE-BACKTEST-EVAL-FRAMEWORK-2026-03-24
**Dominios**: 07_ADAPTIVE_LEARNING · 10_INFRASTRUCTURE_RESILIENCY
**Sprint Mínimo Viable**: HU 7.8 → HU 7.11 → HU 7.6 → HU 7.7 → HU 10.7

## 📋 Tareas del Sprint

- [DONE] **HU 7.8: Contexto estructural declarado en sys_strategies**
  - DDL: `required_regime TEXT DEFAULT 'ANY'`, `required_timeframes TEXT DEFAULT '[]'`, `execution_params TEXT DEFAULT '{}'` en `sys_strategies`
  - Migration automática idempotente en `run_migrations()`
  - Poblar 6 estrategias existentes con valores derivados de su lógica

- [DONE] **HU 7.11: Cadena de fallback multi-proveedor — eliminar síntesis**
  - Reemplazar `_synthesise_cluster_window()` con fallback: proveedor primario → ventana extendida (3000 bars) → proveedores secundarios → `UNTESTED_CLUSTER` (confidence=0.0)
  - `_synthesise_cluster_window()` eliminar del path de producción

- [DONE] **HU 7.6: Interfaz estándar de evaluación histórica en estrategias**
  - `TradeResult` dataclass en `models/trade_result.py`
  - Contrato `evaluate_on_history(df, params) -> List[TradeResult]` en `BaseStrategy`
  - Implementación en las 6 estrategias existentes

- [DONE] **HU 7.7: Simulación real por estrategia — despacho a lógica propia**
  - Reemplazar modelo momentum genérico en `ScenarioBacktester._simulate_trades()`
  - Despacho a `strategy.evaluate_on_history()` via `StrategyEngineFactory`

- [DONE] **HU 10.7: Adaptive Operational Mode Manager**
  - `OperationalModeManager` — detección de contexto (BACKTEST_ONLY / SHADOW_ACTIVE / LIVE_ACTIVE)
  - Ajuste de frecuencias / suspensión de componentes por contexto
  - `get_backtest_budget()` con evaluación de recursos via `psutil`
  - Wiring en `main_orchestrator.py`

## 📊 Snapshot de Cierre

- **Tests añadidos**: 151 (23 HU10.7 + 7 HU7.7 + 11 HU7.11 + 58 HU7.6 + 9 HU7.8 + 121 backtest_orchestrator + 23 oper. mode; sin regresiones)
- **Archivos nuevos**: `models/trade_result.py`, `core_brain/operational_mode_manager.py`, `tests/test_schema_strategy_context_columns.py`, `tests/test_backtester_untested_cluster_policy.py`, `tests/test_strategy_evaluate_on_history.py`, `tests/test_backtester_dispatch_to_strategy.py`, `tests/test_operational_mode_manager.py`
- **Archivos modificados**: `data_vault/schema.py`, `core_brain/scenario_backtester.py`, `core_brain/backtest_orchestrator.py`, `core_brain/strategies/base_strategy.py`, `core_brain/strategies/{mom_bias,liq_sweep,struc_shift,oliver_velez,session_extension_0001,trifecta_logic}.py`, `core_brain/main_orchestrator.py`
- **Deuda técnica eliminada**: síntesis gaussiana removida del path de producción; modelo momentum genérico reemplazado por despacho real por estrategia
- **Estado final**: Sprint Mínimo Viable completado — E10 operativa y verificada

---

# SPRINT 6: SHADOW ACTIVATION — BUCLE DARWINIANO — [DONE]

**Inicio**: 23 de Marzo, 2026
**Fin**: 23 de Marzo, 2026
**Objetivo**: Activar el bucle de evaluación SHADOW End-to-End: implementar `evaluate_all_instances()` real, conectar persistencia en `sys_shadow_performance_history`, clasificar instancias con 3 Pilares y feedback loop horario en MainOrchestrator.
**Épica**: E8 | **Trace_ID**: EXEC-V4-SHADOW-INTEGRATION
**Dominios**: 06_PORTFOLIO_INTELLIGENCE
**Estado Final**: CRÍTICO-1 resuelto. Bucle Darwiniano operativo. Feedback loop horario activo.

## 📋 Tareas del Sprint

- [DONE] **HU 6.4: SHADOW Activation — Bucle Darwiniano Operativo**
  - `shadow_db.py`: `list_active_instances()` (query `sys_shadow_instances` NOT IN DEAD/PROMOTED) + `update_parameter_overrides()` para EdgeTuner
  - `shadow_manager.py`: STUB eliminado. `evaluate_all_instances()` implementado con flujo completo:
    - `storage.list_active_instances()` → instancias reales desde DB
    - `_get_current_regime()` → consulta `RegimeClassifier` (TREND/RANGE/CRASH/NORMAL)
    - `_build_regime_adjusted_validator()` → thresholds contextualizados por régimen
    - 3 Pilares reales por instancia → `record_performance_snapshot()` → `sys_shadow_performance_history` ✅
    - `update_shadow_instance()` → status persistido en `sys_shadow_instances` ✅
    - `log_promotion_decision()` → `sys_shadow_promotion_log` para instancias HEALTHY ✅
    - `_apply_edge_tuner_overrides()` → `parameter_overrides` ajustados por instancia vía EdgeTuner ✅
  - `main_orchestrator.py`: `ShadowManager` recibe `regime_classifier` + `EdgeTuner` via DI. Trigger: semanal → **horario** (`hours_since_last >= 1.0`)
  - `documentation_audit.py`: ruta corregida `docs/SYSTEM_LEDGER.md` → `governance/SYSTEM_LEDGER.md`

> **Snapshot de cierre**: STUB eliminado. Flujo de datos real: DB → RegimeClassifier → 3 Pilares → persistencia doble (history + status) → EdgeTuner override por instancia → feedback loop cada hora.

---

# SPRINT 5: CTRADER WEBSOCKET DATA PROTOCOL — [DONE]

**Inicio**: 21 de Marzo, 2026
**Fin**: 21 de Marzo, 2026
**Objetivo**: Completar el conector cTrader como proveedor de datos FOREX primario implementando el protocolo WebSocket protobuf de Spotware Open API. Corregir los endpoints REST de ejecución. El sistema debe obtener OHLC bars reales desde cTrader sin depender de Yahoo como fallback para FOREX.
**Épica**: E7 | **Trace_ID**: CTRADER-WS-PROTO-2026-03-21
**Dominios**: 00_INFRA, 05_UNIVERSAL_EXECUTION
**Estado Final**: 40/40 tests PASSED | EURUSD M5 fetch real verificado (25 bars Thursday, 10 bars con anchor weekend)

## 📋 Tareas del Sprint

- [DONE] **N1-7: cTrader WebSocket Protocol — OHLC via Protobuf**
  - Instalado `ctrader-open-api` (--no-deps, sin Twisted) + `protobuf` ya disponible.
  - Parcheado `ctrader_open_api/__init__.py`: graceful import fallback para Twisted no instalado en Windows.
  - Implementado `_fetch_bars_via_websocket()` — 4-step Spotware Open API asyncio: APP_AUTH → ACCOUNT_AUTH → SYMBOLS_LIST → GET_TRENDBARS.
  - Implementados helpers: `_build_app_auth_req`, `_build_acct_auth_req`, `_build_symbols_list_req`, `_build_trendbars_req`, `_parse_proto_response`, `_decode_trendbars_response` (delta-encoding: low + deltaOpen/Close/High).
  - Caché de symbol IDs (`EURUSD` → symbolId=1) y digits cache para evitar lookups repetidos por sesión.
  - `_get_last_market_close_ts()`: anchor al viernes 21:00 UTC cuando el mercado está cerrado (fin de semana).
  - Corregido `execute_order`: `api.spotware.com/connect/tradingaccounts/{ctid}/orders?oauth_token=...`
  - Corregido `get_positions`: `api.spotware.com/connect/tradingaccounts/{ctid}/positions?oauth_token=...`
  - Actualizado `_build_config` con `ctid_trader_account_id` parameter.
  - Guardado `ctid_trader_account_id=46662210` + `account_name` en `sys_data_providers.additional_config` DB.
  - Tests TDD: 40/40 PASSED (añadidos `TestCTraderProtobufHelpers` + `test_config_loads_ctid_trader_account_id`).
  - Verificación E2E: fetch real EURUSD M5 confirmado con datos auténticos de precio (1.1540-1.1570 rango).

---

# SPRINT 4: SSOT ENFORCEMENT & DB LEGACY PURGE — [DONE]

**Inicio**: 21 de Marzo, 2026
**Fin**: 21 de Marzo, 2026
**Objetivo**: Eliminar la BD legacy `data_vault/aethelgard.db` y garantizar SSOT único en `data_vault/global/aethelgard.db`.
**Épica**: E6 | **Trace_ID**: DB-LEGACY-PURGE-2026-03-21
**Estado Final**: 7/7 tests PASSED | 0 referencias legacy en producción

## 📋 Tareas del Sprint

- [DONE] **N0-5: Legacy DB Purge & SSOT Enforcement**
  - Eliminado `data_vault/aethelgard.db` del disco.
  - Corregido `data_vault/base_repo.py`: fallback path → `global/aethelgard.db`.
  - Corregido `core_brain/health.py`: `db_path` → `DATA_DIR / "global" / "aethelgard.db"`.
  - Corregido `core_brain/strategy_loader.py`: default `db_path` → `data_vault/global/aethelgard.db`.
  - Eliminado bloque de sync legacy en `core_brain/api/routers/market.py`.
  - Actualizados scripts: `cleanup_db.py`, `db_uniqueness_audit.py`, `check_correct_db.py`.
  - Actualizado `tests/verify_architecture_ready.py`.
  - Tests TDD: `tests/test_db_legacy_purge.py` — 7/7 PASSED.

---

# SPRINT 2: SUPREMACÍA DE EJECUCIÓN (Risk Governance) — [DONE]

**Inicio**: 27 de Febrero, 2026  
**Fin**: 28 de Febrero, 2026  
**Objetivo**: Establecer el sistema nervioso central de gestión de riesgo institucional (Dominio 04) y asegurar la integridad del entorno base.  
**Versión Target**: v4.0.0-beta.1  
**Estado Final**: ✅ COMPLETADO | 6/6 tareas DONE | Cero regresiones (61/61 tests PASSED)

---

## 📋 Tareas del Sprint

- [DONE] **Path Resilience (HU 10.2)**
  - Script agnóstico `validate_env.py` para verificar salud de infraestructura.
  - Validación de rutas, dependencias, variables de entorno y versiones de Python.

- [DONE] **Safety Governor & Sovereignty Gateway (HU 4.4)**
  - TDD implementado (`test_safety_governor.py`).
  - Lógica de Unidades R implementada en `RiskManager.can_take_new_trade()`.
  - Veto granular para proteger el capital institucional (`max_r_per_trade`).
  - Generación de `RejectionAudit` ante vetos.
  - Endpoint de dry-run validation expuesto en `/api/risk/validate`.

- [DONE] **Exposure & Drawdown Monitor Multi-Tenant (HU 4.5)**
  - TDD implementado (`test_drawdown_monitor.py`).
  - Monitoreo en tiempo real de picos de equidad y umbrales de Drawdown (Soft/Hard).
  - Aislamiento arquitectónico garantizado por Tenant_ID.
  - Endpoint de monitoreo expuesto en `/api/risk/exposure`.

- [DONE] **Institutional Footprint Core (HU 3.2)**
  - Creado `LiquidityService` con detección de FVG y Order Blocks.
  - Integrado en `RiskManager.can_take_new_trade` mediante `[CONTEXT_WARNING]`.
  - TDD implementado (`test_liquidity_service.py`).

- [DONE] **Sentiment Stream Integration (HU 3.4 - E3)**
  - Creado `core_brain/services/sentiment_service.py` con enfoque API-first y fallback heurístico institucional.
  - Integrado veto macro en `RiskManager.can_take_new_trade` mediante `[SENTIMENT_VETO]`.
  - Snapshot de sesgo macro persistido en `signal.metadata["institutional_sentiment"]`.

- [DONE] **Depredación de Contexto / Predator Sense (HU 2.2 - E3)**
  - Extendido `ConfluenceService` con detección de barrido de liquidez inter-mercado (`detect_predator_divergence`).
  - Expuesto endpoint operativo `/api/analysis/predator-radar`.
  - UI: widget `Predator Radar` en `AnalysisPage` para monitoreo de `divergence_strength` en tiempo real.

---

## 📸 Snapshot de Contexto

| Métrica | Valor |
|---|---|
| **Estado de Riesgo** | Gobernanza R-Unit Activa y Drawdown Controlado |
| **Resiliencia de Entorno** | Verificada (100% path agnostic) |
| **Integridad TDD** | 61/61 tests PASSED (Cero Regresiones) |
| **Arquitectura** | SSOT (Unica DB), Endpoints Aislados |
| **Versión Global** | v4.0.0-beta.1 |

---

# SPRINT 3: COHERENCIA FRACTAL & ADAPTABILIDAD (Dominio Sensorial)

**Inicio**: 1 de Marzo, 2026  
**Objetivo**: Establecer la supremacía analítica mediante detección de anomalías, meta-coherencia de modelos y auto-calibración adaptativa.  
**Versión Target**: v4.1.0-beta.3  
**Dominios**: 02, 03, 06, 07, 10  
**Estado**: [DONE]

---

## 📋 Tareas del Sprint 3

- [DONE] **Multi-Scale Regime Vectorizer (HU 2.1)**
  - ✅ Unificación de temporalidades para decisión coherente.
  - ✅ Motor RegimeService con lectura de M15, H1, H4.
  - ✅ Regla de Veto Fractal (H4=BEAR + M15=BULL → RETRACEMENT_RISK).
  - ✅ Widget "Fractal Context Manager" en UI.
  - ✅ Sincronización de Ledger (SSOT).
  - ✅ 15/15 Tests PASSED.

- [TODO] **Depredación de Contexto / Predator Sense Optimization (HU 2.2 - Extensión)**
  - Optimización del scanner `detect_predator_divergence` con métricas de predicción.
  - Validación cruzada inter-mercado para alta fidelidad.

- [DONE] **Anomaly Sentinel - Detección de Cisnes Negros (HU 4.6)**
  - ✅ Monitor de eventos de baja probabilidad (volatilidad extrema) con Z-Score > 3.0
  - ✅ Flash Crash Detector (caída > -2% en 1 vela)
  - ✅ Protocolo defensivo: Lockdown Preventivo + Cancel Orders + SL->Breakeven
  - ✅ Persistencia en DB (anomaly_events table) con Trace_ID
  - ✅ Broadcast [ANOMALY_DETECTED] vía WebSocket
  - ✅ Thought Console endpoints (6 routers) + sugerencias inteligentes
  - ✅ Integración con Health System (modo NORMAL/CAUTION/DEGRADED/STRESSED)
  - ✅ 21/21 Tests PASSED | validate_all.py: 100% OK

- [DONE] **Coherence Drift Monitoring (HU 6.3)**
  - Algoritmo de divergencia: modelo esperado vs ejecución en vivo.
  - Alerta temprana de deriva técnica.

- [DONE] **Asset Efficiency Score Gatekeeper (HU 7.2)**
  - ✅ Tabla `strategies` con campos class_id, mnemonic, affinity_scores (JSON), market_whitelist
  - ✅ Tabla `strategy_performance_logs` para logging relacional de desempeño por activo
  - ✅ StrategyGatekeeper: componente en-memory ultra-rápido (< 1ms latencia)
  - ✅ Validación pre-tick: `can_execute_on_tick()` verifica score >= min_threshold
  - ✅ Abort execution automático si asset no cumple (veto)
  - ✅ Market whitelist enforcement: control de activos permitidos
  - ✅ Learning integration: `log_asset_performance()` → strategy_performance_logs
  - ✅ Cálculo dinámico: `calculate_asset_affinity_score()` con ponderación (0.5 win_rate, 0.3 pf_score, 0.2 momentum)
  - ✅ Refresh en-memory: `refresh_affinity_scores()` sincroniza con DB
  - ✅ 17/17 Tests PASSED | validate_all.py: 14/14 modules PASSED
  - ✅ Documentación completa en AETHELGARD_MANIFESTO.md (Sección VI)
  - Trace_ID: EXEC-EFFICIENCY-SCORE-001

- [TODO] **Confidence Threshold Adaptive (HU 7.1)**

- [TODO] **Autonomous Heartbeat & Self-Healing (HU 10.1)**
  - Monitoreo vital continuo (CPU, memoria, conectividad).
  - Auto-recuperación de servicios degradados.

---

## 📸 Snapshot Sprint 3 (Progreso: 2/6 - HU 2.1 + HU 4.6)

| Métrica | Valor |
|---|---|
| **Arquitectura Base** | v4.0.0-beta.1 (18 módulos core + 9 servicios) |
| **Versión Target** | v4.1.0-beta.3 |
| **HU 2.1 Status** | ✅ COMPLETADA (RegimeService, FractalContext, Tests 15/15) |
| **HU 4.6 Status** | ✅ COMPLETADA (AnomalyService, 6 API endpoints, Tests 21/21) |
| **Validación Sistema** | ✅ 14/14 PASSED (validate_all.py) |
| **Total Tests** | 82/82 PASSED (Cero deuda, sin regresiones) |
| **Épica Activa** | E3: Dominio Sensorial & Adaptabilidad |
| **Última Actualización** | 1 de Marzo, 2026 - 20:45 UTC

---

# SPRINT 4: INTEGRACIÓN SENSORIAL Y ORQUESTACIÓN — [DONE]

**Inicio**: 2 de Marzo, 2026  
**Objetivo**: Integrar la capa sensorial completa con orquestación centralizada y expandir capacidades de usuario hacia empoderamiento operativo.  
**Versión Target**: v4.2.0-beta.1  
**Dominios**: 02, 03, 05, 06, 09  
**Estado**: [DONE]

---

## 📋 Tareas del Sprint 4

- [DONE] **Market Structure Analyzer Sensorial (HU 3.3)** (DOC-STRUC-SHIFT-2026)
  - ✅ Sensor de detección HH/HL/LH/LL con caching optimizado
  - ✅ Breaker Block mapping y Break of Structure (BOS) detection
  - ✅ Pullback zone calculation con tolerancia configurable
  - ✅ 14/14 Tests PASSED | Integración en StructureShift0001Strategy

- [DONE] **Orquestación Conflict Resolver (HU 5.2, 6.2)** (EXEC-ORCHESTRA-001)
  - ✅ ConflictResolver: Resolución automática de conflictos multi-estrategia
  - ✅ Jerarquía de prioridades: FundamentalGuard → Asset Affinity → Régimen Alignment
  - ✅ Risk Scaling dinámico según régimen (1.0× a 0.5×)

- [DONE] **UI Mapping Service & Terminal 2.0 (HU 9.1, 9.2)** (EXEC-ORCHESTRA-001)
  - ✅ UIDrawingFactory con paleta Bloomberg Dark (16 colores)
  - ✅ Sistema de 6 capas (Layers): Structure, Targets, Liquidity, MovingAverages, RiskZones, Labels
  - ✅ Elemento visual base (DrawingElement) con z-index automático
  - ✅ Emisión en tiempo real vía WebSocket a UI

- [DONE] **Strategy Heartbeat Monitor (HU 10.1)** (EXEC-ORCHESTRA-001)
  - ✅ StrategyHeartbeat: Monitoreo individual de 6 estrategias (IDLE, SCANNING, POSITION_ACTIVE, etc)
  - ✅ SystemHealthReporter: Health Score integral (CPU, Memory, Conectividad, Estrategias)
  - ✅ Persistencia en BD cada 10 segundos

- [TODO] **E5: User Empowerment (HU 9.3 - 🔴 BLOQUEADO)**
  - ✅ Backend: Manual de Usuario Interactivo (estructurado)
  - ✅ Backend: Sistema de Ayuda Contextual en JSON (description fields)
  - ✅ Backend: Monitoreo de Salud (Heartbeat integrado)
  - ❌ Frontend: Auditoría de Presentación (React renderization failing)
  - 🔴 **BLOQUEADO HASTA**: Validación visual real de WebSocket messages en componentes React
  - **Próximos Pasos**: Auditoría de SocketService, deserialization, layer filtering en React

- [DONE] **Shadow Evolution Frontend UI** (SHADOW-EVOLUTION-UI-2026-001)
  - ShadowHub.tsx · CompetitionDashboard.tsx · JustifiedActionsLog.tsx · EdgeConciensiaBadge.tsx
  - ShadowContext.tsx con useShadow() hook · TypeScript 100% · Build SUCCESS (5.40s)

- [DONE] **Shadow WebSocket Backend Integration** (SHADOW-WS-INTEGRATION-2026-001)
  - Router `GET /ws/shadow` con JWT validation + tenant isolation
  - `emit_shadow_status_update()` en MainOrchestrator · 25/25 validate_all PASSED

---

## 📸 Snapshot Sprint 4 (Progreso: 4/5 - Implementación completada, documentación en progreso)

| Métrica | Valor |
|---|---|
| **Arquitectura Base** | v4.1.0-beta.3 (94 tests, 99.8% compliance) |
| **Versión Target** | v4.2.0-beta.1 |
| **Implementación Status** | ✅ 4/4 Componentes Backend COMPLETADOS |
| **Testing** | ✅ 82/82 PASSED (sin regresiones) |
| **Validación Sistema** | ✅ 14/14 módulos PASSED (validate_all.py) |
| **Épica Activa** | E3-E5: Sensorial → Orquestación → Empoderamiento |
| **Última Actualización** | 2 de Marzo, 2026 - 15:30 UTC

---

# SPRINT N1: FOREX CONNECTIVITY STACK — [DONE]

**Inicio**: 14 de Marzo, 2026
**Fin**: 15 de Marzo, 2026
**Objetivo**: Establecer el stack de conectividad FOREX como capa operacional completa. cTrader como conector primario (WebSocket nativo, sin DLL). MT5 estabilizado. ConnectivityOrchestrator 100% data-driven.
**Versión Target**: v4.3.2-beta
**Estado Final**: ✅ COMPLETADO | 6/6 tareas DONE | 25/25 validate_all PASSED
**Trace_ID**: CONN-SSOT-NIVEL1-2026-03-15

---

## 📋 Tareas del Sprint N1

- [DONE] **N1-1: MT5 Single-Thread Executor**
  - ✅ `_MT5Task` dataclass + `_dll_executor_loop` + cola de mensajes implementados
  - ✅ Race condition eliminada entre threads MT5-Background, `_schedule_retry()` y FastAPI caller
  - ✅ MT5 estable como conector alternativo FOREX

- [DONE] **N1-2: cTrader Connector**
  - ✅ `connectors/ctrader_connector.py` creado (~200 líneas, hereda `BaseConnector`)
  - ✅ WebSocket Spotware Open API: tick/OHLC streaming M1 nativo (<100ms latencia)
  - ✅ REST order execution implementado
  - ✅ cTrader posicionado como conector primario FOREX (priority=100)

- [DONE] **N1-3: Data Stack FOREX default**
  - ✅ Prioridades en `DataProviderManager`: cTrader=100, MT5=70, TwelveData/Yahoo=disabled
  - ✅ M1 desactivado por defecto (`enabled: false`) en config
  - ✅ Stocks/futuros deshabilitados hasta Nivel 2

- [DONE] **N1-4: Warning latencia M1**
  - ✅ `ScannerEngine._scan_one()`: detecta provider no-local + M1 activo
  - ✅ WARNING en log + entrada `usr_notifications` con `category: DATA_RISK`

- [DONE] **N1-5: StrategyGatekeeper → MainOrchestrator**
  - ✅ `StrategyGatekeeper` instanciado vía DI en `MainOrchestrator`
  - ✅ Conectado al flujo de señales pre-ejecución (17/17 tests PASSED)

- [DONE] **N1-6: Provisión + Estabilización cTrader** *(15-Mar-2026)*
  - ✅ Bug fix: `client_secret` hardcodeado `""` → `self.config.get("client_secret", "")`
  - ✅ Seed placeholder `ic_markets_ctrader_demo_20001` en `demo_broker_accounts.json`
  - ✅ Script `scripts/utilities/setup_ctrader_demo.py` con guía OAuth2 interactiva
  - ✅ Bug fix MT5 re-activation: `_sync_sys_broker_accounts_to_providers()` preserva `enabled` del usuario
  - ✅ **Refactor arquitectónico**: `_CONNECTOR_REGISTRY` Python eliminado. `load_connectors_from_db()` lee `connector_module`/`connector_class` de `sys_data_providers` vía `importlib`. Zero código por conector.
  - ✅ Schema migration: columnas `connector_module`, `connector_class` en `sys_data_providers` (aditivo)
  - ✅ `save_data_provider()`: `INSERT OR REPLACE` → `INSERT ... ON CONFLICT DO UPDATE SET ... COALESCE(...)` (preserva datos existentes)
  - ✅ `data_providers.json` seed: `connector_module`/`connector_class` en todos los providers

---

## 📸 Snapshot Sprint N1 (Final)

| Métrica | Valor |
|---|---|
| **Versión Sistema** | v4.3.2-beta |
| **Tareas Completadas** | 6/6 ✅ |
| **validate_all.py** | 25/25 PASSED ✅ |
| **Conectores operativos** | cTrader (primary), MT5 (standby), Yahoo (data fallback) |
| **Arquitectura** | DB-driven connector loading — zero hardcoding |
| **Regresiones** | 0 |
| **Fecha Cierre** | 15 de Marzo, 2026 |

---

# SPRINT N2: SEGURIDAD & VISUALIZACIÓN EN VIVO — [DONE]

**Inicio**: 15 de Marzo, 2026
**Fin**: 16 de Marzo, 2026
**Objetivo**: Estandarizar la seguridad WebSocket (auth production-ready), desbloquear la visualización en tiempo real en React y activar el filtro de veto por calendario económico.
**Versión Target**: v4.4.0-beta
**Estado Final**: ✅ COMPLETADO | 5/5 tareas DONE | 25/25 validate_all PASSED
**Épicas**: E3 (HU 9.3, HU 4.7) · E4 (N2-2, N2-1) · HU 5.2

---

## 📋 Tareas del Sprint

- [DONE] **N2-2: WebSocket Auth Standardization** *(🔴 SEGURIDAD — 15-Mar-2026)*
  - ✅ `get_ws_user()` creado en `auth.py` — única dependencia WS del sistema (cookie → header → query, sin fallback demo)
  - ✅ `_verify_token()` eliminado de `strategy_ws.py` y `telemetry.py`
  - ✅ Bloque fallback demo eliminado de `telemetry.py` y `shadow_ws.py` (vulnerabilidad crítica cerrada)
  - ✅ 3 routers refactorizados: `strategy_ws.py`, `telemetry.py`, `shadow_ws.py`
  - ✅ 16/16 tests PASSED (`test_ws_auth_standardization.py`)
  - ✅ 25/25 validate_all.py PASSED — sin regresiones
  - Trace_ID: WS-AUTH-STD-N2-2026-03-15

- [DONE] **HU 9.3: Frontend WebSocket Rendering** *(15-Mar-2026)*
  - **Root causes corregidos (4)**:
    - RC-A: URL hardcodeada `localhost:8000` en `useSynapseTelemetry`, `AethelgardContext`, `useAnalysisWebSocket` — bypassaba proxy Vite, cookie `a_token` nunca se enviaba.
    - RC-B: `localStorage.getItem('access_token')` en `useStrategyMonitor` — siempre `null` (auth via cookie HttpOnly).
    - RC-C: Prop default `ws://localhost:8000/ws/shadow` en `ShadowHub` — mismo problema cross-origin.
    - RC-D: `useSynapseTelemetry` huérfano — hook completo pero sin consumidor en ningún componente.
  - **Solución**: `ui/src/utils/wsUrl.ts` — función `getWsUrl(path)` usa `window.location.host` para respetar el proxy Vite en dev.
  - **Archivos modificados**: `useStrategyMonitor.ts`, `useSynapseTelemetry.ts`, `AethelgardContext.tsx`, `useAnalysisWebSocket.ts`, `ShadowHub.tsx`, `MonitorPage.tsx`.
  - **Archivos creados**: `ui/src/utils/wsUrl.ts`, `src/__tests__/utils/wsUrl.test.ts`, `src/__tests__/hooks/useStrategyMonitor.test.ts`.
  - **Wiring Glass Box Live**: `MonitorPage` consume `useSynapseTelemetry` mostrando CPU, Memory, Risk Mode, Anomalías en tiempo real vía `/ws/v3/synapse`.
  - ✅ 84/84 vitest PASSED · ✅ 25/25 validate_all.py PASSED

- [DONE] **N2-1: JSON_SCHEMA Interpreter** *(23-Mar-2026)*
  - **Root causes corregidos (4)**:
    - F1: `sys_strategies` sin columnas `type`/`logic` → migración `ALTER TABLE` idempotente en `schema.py`.
    - F2: `_instantiate_json_schema_strategy()` descartaba el spec → pre-carga en `engine._schema_cache` desde el factory.
    - F3: `_calculate_indicators()` leía de `self._schema_cache` roto (siempre `{}`) → ahora recibe `strategy_schema` como parámetro.
    - F4: `eval()` con `__builtins__: {}` (OWASP A03 injection) → reemplazado por `SafeConditionEvaluator`.
  - **`SafeConditionEvaluator`**: clase nueva en `universal_strategy_engine.py`. Evalúa condiciones `"RSI < 30"`, `"RSI < 30 and MACD > 0"`, `"RSI > 70 or MACD > 0"`. Operadores: `<`, `>`, `<=`, `>=`, `==`, `!=`. Fail-safe: cualquier indicador desconocido o formato inválido → `False`. Sin `eval()`/`exec()`.
  - **Archivos modificados**: `data_vault/schema.py`, `data_vault/strategies_db.py`, `core_brain/universal_strategy_engine.py`, `core_brain/services/strategy_engine_factory.py`.
  - **Tests creados**: `tests/test_json_schema_interpreter.py` (25 tests: SafeConditionEvaluator ×14, DB migration ×4, execute_from_registry ×4, _calculate_indicators ×2, factory ×1).
  - ✅ 25/25 tests PASSED · ✅ 25/25 validate_all.py PASSED
  - Trace_ID: N2-1-JSON-SCHEMA-INTERPRETER-2026

- [DONE] **HU 4.7: Economic Calendar Veto Filter** *(CAUTION reduction completada)*
  - **Gap implementado**: bloque CAUTION en `run_single_cycle()` — volumen reducido al 50% para señales BUY/SELL en símbolos con evento MEDIUM activo (floor 0.01).
  - **Comentarios renombrados**: `PHASE 8` → `Step 4a` y `N1-5` → `Step 4b` para consistencia con convención `Step N` del método.
  - **Scripts actualizados**: `economic_veto_audit.py` contador actualizado de 17 → 20 tests.
  - **Archivos modificados**: `core_brain/main_orchestrator.py`, `scripts/utilities/economic_veto_audit.py`.
  - **Archivos de test**: `tests/test_economic_veto_interface.py` (+3 tests: caution reduce 50%, floor 0.01, no-caution sin cambio).
  - ✅ 20/20 tests PASSED · ✅ 25/25 validate_all.py PASSED

- [DONE] **HU 5.2: Adaptive Slippage Controller** *(SSOT desde DB)*
  - **Problema raíz**: `self.default_slippage_limit = Decimal("2.0")` hardcodeado en `ExecutionService` — ignoraba volatilidad por asset class (GBPJPY vetado igual que EURUSD). Violación de SSOT (límites en código, no en DB).
  - **Solución**:
    - `SlippageController` nuevo (`core_brain/services/slippage_controller.py`) — límites por asset class + multiplicadores de régimen leídos de `dynamic_params["slippage_config"]` (DB, SSOT). p90 auto-calibración desde `usr_execution_logs`.
    - `market_type` pasado explícitamente por el caller desde `signal.metadata` — cero detección por nombre de símbolo.
    - Fallback `_DEFAULT_CONFIG` solo en bootstrap (DB vacía).
    - `get_slippage_p90(symbol, min_records)` agregado a `ExecutionMixin` — lee `ABS(slippage_pips)` de `usr_execution_logs`.
    - `ExecutionService.__init__` ahora recibe `slippage_controller: SlippageController` (DI obligatoria).
    - `OrderExecutor` instancia `SlippageController(storage)` e inyecta en `ExecutionService`.
    - Override por señal preservado: `signal.metadata["slippage_limit"]` tiene prioridad absoluta.
  - **Archivos creados**: `core_brain/services/slippage_controller.py`, `tests/test_slippage_controller.py` (17 tests: base limits ×6, regime multipliers ×4, p90 calibration ×4, integration ×3).
  - **Archivos modificados**: `core_brain/services/execution_service.py`, `core_brain/executor.py`, `data_vault/execution_db.py`.
  - ✅ 17/17 tests PASSED · ✅ 25/25 validate_all.py PASSED
  - Trace_ID: HU-5.2-ADAPTIVE-SLIPPAGE-2026

---

## 📸 Snapshot Sprint N2 (Final)

| Métrica | Valor |
|---|---|
| **Versión Sistema** | v4.4.0-beta |
| **Tareas Completadas** | 5/5 ✅ |
| **validate_all.py** | 25/25 PASSED ✅ |
| **Suite de Tests** | 1441 passed · 0 failed · 0 skipped · 0 warnings |
| **Seguridad** | WebSocket auth production-ready (vulnerabilidad crítica cerrada) |
| **Cobertura** | WebSocket rendering React · Economic veto · Slippage adaptativo · JSON schema |
| **Regresiones** | 0 |
| **Fecha Cierre** | 16 de Marzo, 2026 |

# SPRINT N6: FEED INTEGRATION & RATE LIMITS — [DONE]

**Inicio**: 17 de Marzo, 2026  
**Fin**: 17 de Marzo, 2026  
**Objetivo**: Corregir instanciación en ConnectivityOrchestrator y manejar el agotamiento del Free Tier en Alpha Vantage de forma resiliente.  
**Versión Target**: v4.4.4-beta  
**Estado Final**: ✅ COMPLETADO | 2/2 tareas DONE | validate_all 100% PASSED  
**Épica**: E6 (Estabilización Core)  
**HUs**: HU 5.5, HU 5.6  
**Trace_ID**: RUNTIME-FIX-FEEDS-2026-N6

---

## 📋 Tareas del Sprint N6

- [DONE] **T1: Inyección Selectiva en ConnectivityOrchestrator** *(HU 5.5)*
  - Filtrar `kwargs` con `inspect.signature` antes de instanciar providers en `load_connectors_from_db()`.
  
- [DONE] **T2: Manejar Rate Limits de Alpha Vantage** *(HU 5.6)*
  - Bajar severidad de limit/no time series data en AlphaVantageProvider. Retornar `None` silenciosamente.
  - Se agregó `provider_id` a la clase `AlphaVantageProvider` para alinear el contrato de `ConnectivityOrchestrator`.

---

## 📸 Snapshot Sprint N6 (Final)

| Métrica | Valor |
|---|---|
| **Versión Sistema** | v4.4.4-beta |
| **Tareas Completadas** | 2/2 ✅ |
| **validate_all.py** | PASSED ✅ en todos los dominios |
| **Runtime Errors** | Crashes de orquestador eliminados (0 previstos) |
| **Fecha Cierre** | 17 de Marzo, 2026 |

---

# SPRINT N5: CORRECCIÓN RUNTIME CORE — [DONE]

**Inicio**: 17 de Marzo, 2026  
**Fin**: 17 de Marzo, 2026  
**Objetivo**: Resolver `errors=52/52` en ejecución real, corregir inyección de kwargs en providers, e implementar la separación arquitectónica de cuentas de broker (`usr_broker_accounts`).  
**Versión Target**: v4.4.3-beta  
**Estado Final**: ✅ COMPLETADO | 4/4 tareas DONE | validate_all 100% PASSED  
**Épica**: E6 (nueva — Estabilización Core)  
**HUs**: HU 5.4, HU 8.1  
**Trace_ID**: RUNTIME-FIX-COOLDOWN-KWARGS-2026-N5

---

## 📋 Tareas del Sprint N5

- [DONE] **T4: WARNING → DEBUG en RiskManager** *(HU 5.4 - prep)*
  - `logger.warning("[SSOT]...")` → `logger.debug(...)` cuando se usan parámetros por defecto.

- [DONE] **T2: Inyección Selectiva de kwargs en DataProviderManager** *(HU 5.4)*
  - Especificación: `docs/specs/SPEC-T2-provider-kwargs-injection.md`
  - Filtrar kwargs con `inspect.signature` antes de instanciar providers para evitar ValueError.
  - Fixeado instanciación de AlphaVantageProvider y CTraderConnector.

- [DONE] **T1: Métodos de Cooldown en StorageManager** *(HU 5.4)*
  - Especificación: `docs/specs/SPEC-T1-cooldown-storage.md`
  - Implementado `get_active_cooldown`, `register_cooldown`, `clear_cooldown`, `count_active_cooldowns` en `ExecutionMixin`.
  - Agregados tests TDD y añadidos a `validate_all.py`. Resuelve AttributeError en CooldownManager y SignalSelector.

- [DONE] **T3: Implementar `usr_broker_accounts`** *(HU 8.1)*
  - Especificación: `docs/specs/SPEC-T3-usr-broker-accounts.md`
  - DDL insertado en `schema.py` debajo de `sys_data_providers`.
  - Creado `BrokerAccountsMixin` con operaciones CRUD y aislamiento por `user_id`.
  - Script idempotente de migración `migrate_broker_accounts.py` transferió 2 cuentas reales.
  - Tests TDD añadidos en `test_usr_broker_accounts.py` y validados.

---

## 📸 Snapshot Sprint N5 (Final)

| Métrica | Valor |
|---|---|
| **Versión Sistema** | v4.4.3-beta |
| **Tareas Completadas** | 4/4 ✅ |
| **validate_all.py** | PASSED ✅ (incluyendo tests TDD) |
| **Runtime Errors** | Bajado de 52/52 a 0 |
| **Arquitectura** | sys_broker_accounts (DEMO) vs usr_broker_accounts aislando al trader |
| **Fecha Cierre** | 17 de Marzo, 2026 |

---

# SPRINT N4: FIX PROTOCOL CORE — [DONE]

**Inicio**: 18 de Marzo, 2026
**Fin**: 18 de Marzo, 2026
**Épica**: E4 (cierre)
**Objetivo**: Implementar la capa de transporte FIX 4.2 para conectividad con Prime Brokers institucionales.
**Versión Target**: v4.4.2-beta

---

## 📋 Tareas del Sprint

- [DONE] **HU 5.1: FIX Connector Core — librería simplefix + requirements.txt**
  - `simplefix>=1.0.17` añadido a `requirements.txt`.
  - TRACE_ID: FIX-CORE-HU51-2026-001

- [DONE] **HU 5.1: FIX Connector Core — TDD (14 tests)**
  - Creado `tests/test_fix_connector.py` con 14 tests en 5 grupos:
    - Interface & Identity (2) · Logon Handshake (4)
    - Availability Lifecycle (2) · Order Execution (4) · Logout & Latency (2)

- [DONE] **HU 5.1: FIX Connector Core — Implementación FIXConnector**
  - Creado `connectors/fix_connector.py` — hereda `BaseConnector`.
  - Mensajes: Logon (A) · Logout (5) · New Order Single (D) · Execution Report (8).
  - Config SSOT vía `storage.get_data_provider_config("fix_prime")`.
  - `socket_factory` injectable para tests sin broker real.
  - `ConnectorType.FIX = "FIX"` añadido a `models/signal.py`.
  - Bug encontrado y corregido: `simplefix.get(tag, nth)` — 2do arg es ordinal (no default).

---

## 📸 Snapshot Sprint N4 (Final)

| Métrica | Valor |
|---|---|
| **Versión Sistema** | v4.4.2-beta |
| **Tareas Completadas** | 3/3 ✅ |
| **validate_all.py** | 25/25 PASSED ✅ |
| **Suite de Tests** | 1466 passed · 0 failed · 0 skipped · 0 warnings |
| **Nuevos Tests** | +14 (test_fix_connector.py) |
| **Archivos Creados** | `connectors/fix_connector.py` · `tests/test_fix_connector.py` |
| **Archivos Modificados** | `requirements.txt` · `models/signal.py` · `governance/BACKLOG.md` |
| **Regresiones** | 0 |
| **Fecha Cierre** | 18 de Marzo, 2026 |

---

# SPRINT N3: PULSO DE INFRAESTRUCTURA — [DONE]

**Inicio**: 17 de Marzo, 2026
**Fin**: 17 de Marzo, 2026
**Épica**: E3 (cierre)
**Objetivo**: Completar el Dominio Sensorial con el último HU pendiente: telemetría de recursos reales y veto técnico de ciclo.
**Versión Target**: v4.4.1-beta

---

## 📋 Tareas del Sprint

- [DONE] **HU 5.3: The Pulse — psutil en heartbeat**
  - `_get_system_heartbeat()` en `telemetry.py`: reemplazados 3 placeholders (0.0/0) con `psutil.cpu_percent(interval=None)`, `psutil.virtual_memory().used // 1024²` y media de latencia de satélites.
  - `psutil` importado en `telemetry.py`.

- [DONE] **HU 5.3: The Pulse — bloque veto en run_single_cycle()**
  - Bloque veto insertado tras PositionManager y antes del Scanner.
  - Lee `cpu_veto_threshold` de `dynamic_params` (SSOT, default 90%).
  - Si CPU supera umbral: log WARNING, persiste notificación `SYSTEM_STRESS` en `usr_notifications`, retorna sin escanear.
  - PositionManager (trades abiertos) no se ve afectado: corre antes del veto.

- [DONE] **TDD 11/11 — tests/test_infrastructure_pulse.py**
  - 3 grupos: heartbeat psutil · veto CPU · notificación SYSTEM_STRESS
  - 2 grupos adicionales: threshold SSOT · PositionManager isolation
  - Trace_ID: INFRA-PULSE-HU53-2026-001

---

## 📸 Snapshot Sprint N3 (Final)

| Métrica | Valor |
|---|---|
| **Versión Sistema** | v4.4.1-beta |
| **Tareas Completadas** | 3/3 ✅ |
| **validate_all.py** | 25/25 PASSED ✅ |
| **Suite de Tests** | 1452 passed · 0 failed · 0 skipped · 0 warnings |
| **Nuevos Tests** | +11 (test_infrastructure_pulse.py) |
| **Archivos Modificados** | `telemetry.py` · `main_orchestrator.py` |
| **Regresiones** | 0 |
| **Fecha Cierre** | 17 de Marzo, 2026 |

---

# SPRINT N7: REFACTORIZACIÓN MULTI-USUARIO & SANEAMIENTO TELEMÉTRICO — [DONE]

**Inicio**: 17 de Marzo, 2026  
**Fin**: 17 de Marzo, 2026  
**Objetivo**: Eliminar inyecciones hardcodeadas (MT5), separar cuentas de proveedores de datos (`sys_data_providers`) de cuentas de ejecución (`usr_broker_accounts`), garantizando lectura exclusiva desde bases de datos, y silenciar warnings/errors residuales esperados.  
**Versión Target**: v4.5.0-beta  
**Estado Final**: ✅ COMPLETADO | 3/3 tareas DONE | validate_all 100% PASSED  
**Épica**: E5 (Ejecución Agnóstica) y E6 (Estabilización Core)  
**HUs**: HU 5.2.1, HU 5.6b, HU 5.7  
**Trace_ID**: REFACTOR-MULTIUSER-2026-N7

---

## 📋 Tareas del Sprint N7

- [x] **T1: Refactorización Multi-Usuario (HU 5.2.1)**
  - `ConnectivityOrchestrator` modificado para cargar `sys_broker_accounts` y `usr_broker_accounts`.
  - `start.py` limpiado de inyección estática; invoca a `ConnectivityOrchestrator` para orquestar la conexión de la BD y la inyección.
  - Vínculo directo con base de datos establecido (SSOT) garantizando cero configuraciones hardcodeadas.

- [x] **T2: Saneamiento Profundo de Alpha Vantage (HU 5.6b)**
  - Integrada la lógica de `Note` (rate limit message) en endpoints Crypto y Forex para capturarlo silenciosamente.
  - Corregido el mensaje erróneo tipo "stock" en Crypto y pasados los falsos errores a DEBUG/INFO.

- [x] **T3: Saneamiento de Advertencias Normales (HU 5.7)**
  - Mensaje WARMUP de 30s pasado a `logger.info`.
  - Mensaje de NotificationEngine no configurado rebajado a nivel INFO.

---

## 📸 Snapshot Sprint N7 (Final)

| Métrica | Valor |
|---|---|
| **Versión Sistema** | v4.5.0-beta |
| **Tareas Completadas** | 3/3 ✅ |
| **Integridad de BD (SSOT)** | Cero Bases Temporales detectadas ✅ (`aethelgard_system` erradicada) |
| **validate_all.py** | PASSED ✅ en los 25 dominios paralelos |
| **Resolución Multiusuario** | Completada, acoplamiento global erradicado |
| **Fecha Cierre** | 17 de Marzo, 2026 |

---

# SPRINT 7: ESTABILIZACIÓN OPERACIONAL & OBSERVABILIDAD — [DONE]

**Inicio**: 24 de Marzo, 2026
**Fin**: 24 de Marzo, 2026
**Objetivo**: Corregir 9 bugs críticos detectados en auditoría de sistema real (ADX=0, backtest score fantasma, conn_id mismatch, pip_size incorrecto, cooldown sync/async, SHADOW bypass) e implementar el componente `OperationalEdgeMonitor` como capa de observabilidad de invariantes de negocio.
**Épica**: E6 (Estabilización Core)
**Trace_ID**: OPS-STABILITY-EDGE-MONITOR-2026-03-24
**Dominios**: 00_INFRA · 03_SCANNER · 05_EXEC · 06_PORTFOLIO
**Estado Final**: 9 bugs críticos resueltos. OperationalEdgeMonitor operativo (27/27 tests). DB SSOT restaurada.

## 📋 Tareas del Sprint

- [DONE] **T1: Scanner ADX siempre cero**
  - `core_brain/scanner.py`: `classifier.load_ohlc(df)` faltaba antes de `classify()` → ADX=0 en todos los market pulses.
  - Fix: llamada a `load_ohlc(df)` insertada en el flujo de `_scan_one()`.
  - TDD: `TestScannerLoadsOHLC` — `load_ohlc` invocado en cada ciclo.

- [DONE] **T2: Backtest score fantasma (0-trades guard + numpy cast)**
  - `core_brain/scenario_backtester.py`: threshold `0.75` → `0.001` (umbral de entrada numérico); guard para lotes sin trades; cast explícito numpy → Python float en `score_backtest`.
  - TDD: `TestBacktestScoreNotZero` — verificado score > 0 con datos sintéticos.

- [DONE] **T3: conn_id mismatch en Executor**
  - `core_brain/executor.py`: `connector_id` de la cuenta de broker no coincidía con el id registrado en `connectivity_orchestrator.py` por doble registro con alias. Corregido propagando id canónico.
  - `scripts/migrations/migrate_broker_schema.py`: path DB corregido a `__file__`-anchored.

- [DONE] **T4: Cooldown sync/async en SignalSelector**
  - `core_brain/signal_selector.py`: `await self.storage.get_active_cooldown(signal_id)` lanzaba `TypeError: object NoneType can't be used in 'await'` cuando el storage es síncrono.
  - Fix: guard `inspect.iscoroutinefunction` + módulo-level `import inspect, asyncio`.
  - TDD: `TestCooldownSyncStorage` (2 tests) — sync y async path verificados.

- [DONE] **T5: recent_signals dicts + SHADOW bypass Phase 4**
  - `core_brain/main_orchestrator.py`:
    - `recent_signals` eran objetos `Signal` → componentes downstream esperaban `List[Dict]`. Fix: bloque de conversión `model_dump()` / `vars()`.
    - Señales SHADOW entraban al quality gate (Phase 4) → falso veto. Fix: bypass completo cuando `origin_mode == 'SHADOW'`.
  - TDD: `TestPhase4QualityGateShadowBypass` (4 tests).

- [DONE] **T6: pip_size USDJPY incorrecto → error 10016**
  - `core_brain/executor.py`: pip_size JPY `0.0001` → `0.01`; pip_size no-JPY `0.00001` → `0.0001`. Ambos valores estaban desplazados un orden de magnitud.
  - TDD: `TestStopLossDefaultPipSize` (3 tests) — USDJPY, EURUSD y GBPJPY verificados.

- [DONE] **T7: EdgeMonitor warning MT5 spam en log**
  - `core_brain/edge_monitor.py`: `logger.warning("[EDGE] MT5 connector not injected")` se emitía cada 60s.
  - Fix: flag `_mt5_unavailable_logged` → INFO en primera llamada, DEBUG en las siguientes.
  - TDD: `TestEdgeMonitorMT5Warning` (4 tests).

- [DONE] **T8: DB SSOT — `data_vault/aethelgard.db` rogue**
  - `data_vault/aethelgard.db` (0 bytes) creado por scripts de migración con path relativo a CWD.
  - Fix: eliminado el archivo; 4 scripts de migración actualizados a path absoluto `__file__`-anchored con `if not db_path.exists(): return/error` preservado.
  - Scripts afectados: `migrate_broker_schema.py`, `migrate_add_traceability.py`, `migrate_add_timeframe.py`, `migrate_add_price_column.py`.

- [DONE] **FASE 4: OperationalEdgeMonitor — 8 invariantes de negocio**
  - `core_brain/operational_edge_monitor.py`: componente `threading.Thread(daemon=True)` standalone.
  - 8 checks: `shadow_sync`, `backtest_quality`, `connector_exec`, `signal_flow`, `adx_sanity`, `lifecycle_coherence`, `rejection_rate`, `score_stale`.
  - Interfaz pública: `run_checks() → Dict[str, CheckResult]` · `get_health_summary() → {status, checks, failing, warnings}`.
  - Ciclo daemon: 300s por defecto; persiste violaciones en `save_edge_learning()`.
  - TDD: `tests/test_operational_edge_monitor.py` — 27/27 PASSED.

---

## 📸 Snapshot Sprint 7 (Final)

| Métrica | Valor |
|---|---|
| **Versión Sistema** | v4.5.1-beta |
| **Tareas Completadas** | 9/9 ✅ |
| **Suite de Tests** | 1587 passed · 0 failed (producción) |
| **Nuevos Tests** | +40 (T4×2, T5×4, T6×3, T7×4, FASE4×27) |
| **Bugs Críticos Resueltos** | 9 (ADX, backtest, conn_id, cooldown, dicts, SHADOW, pip_size, MT5 log, SSOT) |
| **Nuevo Componente** | `OperationalEdgeMonitor` — observabilidad de invariantes de negocio |
| **DB SSOT** | Restaurada — cero archivos rogue · migraciones path-safe |
| **Regresiones** | 0 |
| **Fecha Cierre** | 24 de Marzo, 2026 |

---

# SPRINT 8: DESBLOQUEO OPERACIONAL DEL PIPELINE — [DONE]

**Inicio**: 24 de Marzo, 2026
**Fin**: 24 de Marzo, 2026
**Objetivo**: Resolver 5 bloqueos operacionales que impiden el flujo BACKTEST→SHADOW→LIVE: filtro de activos en SignalFactory (15/18 símbolos descartados), cooldown de backtest bloqueado por campo incorrecto, EdgeMonitor hardcodeado a MT5, capital hardcodeado, y ausencia de PID lock. Documentar diseño FASE4 AutonomousSystemOrchestrator.
**Épica**: E9 | **Trace_ID**: PIPELINE-UNBLOCK-EDGE-2026-03-24
**Dominios**: 03_ALPHA_GENERATION · 07_LIFECYCLE · 10_INFRA_RESILIENCY
**Estado**: [DONE] 6/6 tareas — E9 COMPLETADA (ver SYSTEM_LEDGER)

## 📋 Tareas del Sprint

- [DONE] **P9 — HU 10.3: Proceso Singleton — PID Lockfile**
  - `start.py`: `_acquire_singleton_lock(lock_path)` + `_release_singleton_lock(lock_path)`. Lockfile en `data_vault/aethelgard.lock`. Aborta si PID activo, sobreescribe PID muerto. Limpia en `finally`.
  - TDD: `tests/test_start_singleton.py` — 9/9 PASSED

- [DONE] **P6 — HU 10.4: Capital desde sys_config**
  - `start.py`: `_read_initial_capital(storage)` — lee `account_balance` de `sys_config`; fallback 10000.0 con WARNING. Inyectado en `RiskManager`.
  - TDD: 4 tests en `tests/test_start_singleton.py` (incluidos en los 9/9 arriba)

- [DONE] **P3 — HU 7.5: Backtest Cooldown — last_backtest_at**
  - `data_vault/schema.py`: columna `last_backtest_at TIMESTAMP DEFAULT NULL` en DDL `sys_strategies` + migration inline en `run_migrations()`. Trace_ID: PIPELINE-UNBLOCK-BACKTEST-COOLDOWN-2026-03-24.
  - `core_brain/backtest_orchestrator.py`: `_is_on_cooldown()` usa `last_backtest_at` (fallback `updated_at` para rows sin el campo); `_update_strategy_scores()` setea `last_backtest_at=CURRENT_TIMESTAMP`; SELECTs incluyen `last_backtest_at`.
  - TDD: +3 tests en `tests/test_backtest_orchestrator.py` — 43/43 PASSED

- [DONE] **P2 — HU 3.9: Signal Factory — InstrumentManager Filter**
  - `core_brain/signal_factory.py`: param `instrument_manager: Optional[Any] = None`; bloque FASE4 reemplazado con `instrument_manager.get_enabled_symbols()`. Fallback a sin-filtro cuando no inyectado.
  - `start.py`: `instrument_manager` inyectado en `SignalFactory`.
  - TDD: `TestInstrumentManagerFilter` — 3 tests en `tests/test_signal_factory.py` (6/6 total PASSED)

- [DONE] **P5 — HU 10.5: EdgeMonitor Connector-Agnóstico**
  - `core_brain/edge_monitor.py`: param `connectors: Dict[str, Any]`. Backward compat: `mt5_connector=` wrapeado como `{"mt5": connector}`. Nuevo método `_get_active_connectors()`. `_get_mt5_connector()` conservado como wrapper para compatibilidad.
  - `start.py`: `EdgeMonitor` recibe `connectors=active_connectors`.
  - TDD: `TestEdgeMonitorConnectorAgnostic` — 6 tests (10/10 total PASSED)

- [DONE] **FASE4 — HU 10.6: AutonomousSystemOrchestrator — Diseño**
  - Documentar diseño completo en `docs/10_AUTONOMOUS_ORCHESTRATOR.md`.
  - Inventario de 13 componentes EDGE existentes + mapa de coordinación.
  - Especificar: DiagnosticsEngine, BaselineTracker, HealingPlaybook, ObservabilityLedger, EscalationRouter.
  - DDL propuesto para `sys_agent_events`.

---

## 📸 Snapshot Sprint 8 (Final)

| Métrica | Valor |
|---|---|
| **Versión Sistema** | v4.6.0-beta |
| **Tareas Completadas** | 6/6 ✅ |
| **Suite de Tests** | 1601 passed · 0 failed |
| **Nuevos Tests** | +22 (P9×9, P3×3, P2×3, P5×6 + actualización test_signal_factory_asset_filtering) |
| **Bugs Críticos Resueltos** | 5 (filtro activos, cooldown backtest, EdgeMonitor MT5, capital hardcoded, proceso duplicado) |
| **HU 10.6 Diseño FASE4** | Completo en `docs/10_INFRA_RESILIENCY.md` (E9 archivada) |
| **Regresiones** | 0 |
| **Fecha Cierre** | 24 de Marzo, 2026 |