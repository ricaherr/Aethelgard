# AETHELGARD: ESTRATEGIC ROADMAP

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Visión estratégica de alto nivel. No es un diario de tareas.
> - **Estructura**: Épicas (`E1, E2...`) con su estado y el Sprint que las ejecuta. Sin checkboxes de subtareas.
> - **Estados de Épica**: `PENDIENTE` · `ACTIVA` · `COMPLETADA`
> - **Al iniciar implementación**: Marcar Épica como `ACTIVA` ANTES de escribir una línea de código.
> - **Al completar Sprint**: Actualizar Épica a `COMPLETADA` + archivar en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS, formato ÉPICA-ARCHIVO) + **ELIMINAR la Épica del ROADMAP**.
> - **NO agregar aquí**: listas de archivos modificados, métricas de tests, detalles de implementación (eso va en SPRINT.md).
> - **Framework completo**: `.ai_orchestration_protocol.md` Sección 4.

**Versión Log**: v4.24.0-beta
**Última Actualización**: 24 de Abril, 2026 (E5-HU5.1 ETI — IncidentLearningEngine, escalada progresiva y notificación inteligente implementados)

---

## 📈 ÉPICAS ESTRATÉGICAS

> ℹ️ Solo se muestran Épicas en estado `ACTIVA` o `PENDIENTE`. Las Épicas `COMPLETADA` se archivan en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS) y se eliminan de este documento.

### E2: Erradicación de Dependencias MT5 y Arquitectura Agnóstica — COMPLETADA ✅
**Sprint**: 33 | **Trace_ID**: ETI-MT5-AUDIT-AGNOSTIC-2026-04-23 | **Fecha**: 2026-04-23
**Objetivo**: Eliminar todos los imports directos de MT5Connector/MetaTrader5 fuera de `connectors/`. Sistema opera igual con cTrader, Yahoo o cualquier otro proveedor sin bloqueos por MT5 ausente.
- `models/symbol_utils.py` — nuevo: `normalize_symbol()` agnóstico
- `connectors/connector_factory.py` — nuevo: SSOT para instanciar conectores por platform_id
- 6 archivos `core_brain/` refactorizados (signal_factory, signal_deduplicator, multi_timeframe_limiter, edge_monitor, health, services/trading_service, api/routers/trading)
- 3 scripts de utilidad actualizados (sin `import MetaTrader5` directo)
- `tests/test_architecture_no_mt5_in_core.py` — blindaje permanente (4 tests de regresión)
- **2881 passed, 3 skipped, 0 failed** ✅
**Criterios AC**: todos cumplidos.

---

### DB-GOV-001: Gobernanza de Bases de Datos Temporales en Scripts Utilitarios — COMPLETADA ✅
**Sprint**: 35 | **Trace_ID**: DB-GOV-TEMP-SCRIPTS-2026-04-23 | **Fecha**: 2026-04-23
**Objetivo**: Garantizar que ningún script utilitario deje archivos .db residuales fuera de las rutas oficiales, con cleanup automático garantizado incluso ante errores.
- `scripts/utilities/script_db_guard.py` — nuevo: `temp_db()`, `purge_residual_dbs()`, `find_residual_dbs()`, `is_allowed_db_path()`
- `scripts/runner.py` — nuevo: ejecutor central con auditoría y cleanup post-ejecución
- `stop.py` — ampliado: `_purge_residual_dbs()` elimina .db fuera de rutas permitidas
- Corrección de paths legacy en 6 scripts (diagnose_instruments, force_init, list_tables, migrate_strategy_registries, purge_database, system_diagnostics)
- `tests/test_script_db_governance.py` — 24/24 TDD GREEN
**Criterios AC**: todos cumplidos.

---

### E4/HU 4.1 — Autoajuste Dinámico de Resiliencia — COMPLETADA ✅
**Sprint**: 33 | **Trace_ID**: ARCH-RESILIENCE-AUTOTUNE-V1 | **Fecha**: 2026-04-22
**Objetivo**: Calibración incremental y auditada de umbrales de LOCKDOWN/STRESSED. El sistema aprende de recuperaciones reales para preservar el EDGE.
- `core_brain/resilience_autotune.py` — nuevo: `ResilienceAutoTuner` (SOFTEN/HARDEN + SSOT)
- `core_brain/resilience_manager.py` — integración AutoTuner (params dinámicos, min_stability_cycles, record_recovery)
- `data_vault/storage.py` — `get_resilience_params()` / `save_resilience_params()`
- `tests/test_resilience_autotune.py` — 25/25 TDD GREEN
**Criterios AC**: todos cumplidos. 25 nuevos + 30 regresión = 55/55 PASSED.

---

### ETI-EDGE-LOCKDOWN-DEGRADATION: Degradación Granular LOCKDOWN — COMPLETADA ✅
**Sprint**: 28 | **Trace_ID**: EDGE_Lockdown_Degradation_Granular_2026-04-16 | **Fecha**: 2026-04-17
**Objetivo**: Reemplazar el protocolo de LOCKDOWN total por degradación granular con close-only mode, preservando la gestión de posiciones abiertas durante crisis.
- `core_brain/close_only_guard.py` — nuevo: CloseOnlyGuard thread-safe con auto-reversión
- `core_brain/services/order_gate.py` — nuevo: OrderGate (bloquea BUY/SELL, permite CLOSE)
- `core_brain/resilience_manager.py` — degradación por módulo, auto-reversión, close-only protocol
- `core_brain/orchestrators/_guard_suite.py` — LOCKDOWN activa close-only, elimina cancel_all
- `core_brain/position_manager.py` — integra CloseOnlyGuard (DI)
- `core_brain/executor.py` — integra OrderGate (DI), check pre-lockdown
- `utils/alerting.py` — AlertEventType EDGE + send_edge_event()
- `tests/test_edge_lockdown_degradation.py` — 36/36 TDD GREEN
**Criterios AC**: todos cumplidos. Tests: 36/36 nuevos + 2701/2701 regresión = 0 fallos.

---

### E5-HU5.1: Aprendizaje Adaptativo y Notificación Inteligente — ACTIVA
**Sprint**: 34 | **Trace_ID**: ETI-ILE-E5HU51-2026-04-24
**Objetivo**: Motor de aprendizaje de incidentes con escalada progresiva (≥2 rutas automáticas), notificación Telegram enriquecida con contexto accionable y feedback loop.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 5.1 | IncidentLearningEngine + escalada autónoma + notificación inteligente | RESILIENCIA | 34 | [IN_PROGRESS] |

**Implementado en este ciclo (2026-04-24)**:
- `core_brain/incident_learning_engine.py` — nuevo: ILE con ROUTE_CATALOG, estadísticas, auto-revert
- `resilience_manager.py` — ILE inyectado, registra rutas en _heal_data_coherence/_heal_database/_escalate_after_exhaustion
- `utils/alerting.py` — `send_incident_alert()`, nuevos AlertEventType INCIDENT_*
- `operational_edge_monitor.py` — feedback loop: `_ile_open_incidents()` + `_ile_check_auto_reverts()`
- `tests/test_incident_learning.py` — 32 tests TDD

---

### E5: Interfaz Fractal & Experiencia Futurista (Ámbito Transversal UI) — ACTIVA
**Sprint**: 25 | **Trace_ID**: UI-V3-FRACTAL-FUTURE-2026
**Objetivo**: Evolucionar la terminal a una consola de alta densidad de información con navegación fractal y elementos de manipulación directa.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 9.4 | Unified Telemetry Stream (The Synapse) | TRANSVERSAL_UI | 25 | [DONE] |
| HU 9.5 | Fractal Zoom Engine | TRANSVERSAL_UI | — | [TODO] |
| HU 9.6 | Direct Manipulation (Drag & Drop) | TRANSVERSAL_UI | — | [TODO] |
| HU 9.7 | Sci-Fi Component Library (HUDs) | TRANSVERSAL_UI | — | [TODO] |
| HU 9.8 | Event Soldering (ANOMALY + REASONING) | TRANSVERSAL_UI | — | [TODO] |

---

### E16: Membresía SaaS, Correlación Multi-Mercado & Darwinismo de Portafolio — ACTIVA
**Sprint**: 27 | **Trace_ID**: E16-SAAS-PORTFOLIO-DARWIN-2026
**Objetivo**: Completar la jerarquía de acceso SaaS (3 tiers), implementar correlación inter-mercado para señales de alta fidelidad, el motor Shadow Reality con penalización real y el ranking darwinista de estrategias por usuario.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 1.3 | User Role & Membership Level (Deuda Técnica) | 01 | 27 | [TODO] |
| HU 3.3 | Multi-Market Alpha Correlator | 03 | 27 | [TODO] |
| HU 6.1 | Shadow Reality Engine (Penalty Injector) | 03 | 27 | [TODO] |
| HU 6.2 | Multi-Tenant Strategy Ranker | 03 | 27 | [TODO] |

---

> El historial completo de épicas completadas se encuentra en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md).
> El protocolo y último informe de auditoría están en [AUDIT_PROTOCOL.md](AUDIT_PROTOCOL.md) y [AUDITORIA_ESTADO_REAL.md](AUDITORIA_ESTADO_REAL.md).
