# AETHELGARD: ESTRATEGIC ROADMAP

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Visión estratégica de alto nivel. No es un diario de tareas.
> - **Estructura**: Épicas (`E1, E2...`) con su estado y el Sprint que las ejecuta. Sin checkboxes de subtareas.
> - **Estados de Épica**: `PENDIENTE` · `ACTIVA` · `COMPLETADA`
> - **Al iniciar implementación**: Marcar Épica como `ACTIVA` ANTES de escribir una línea de código.
> - **Al completar Sprint**: Actualizar Épica a `COMPLETADA` + archivar en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS, formato ÉPICA-ARCHIVO) + **ELIMINAR la Épica del ROADMAP**.
> - **NO agregar aquí**: listas de archivos modificados, métricas de tests, detalles de implementación (eso va en SPRINT.md).
> - **Framework completo**: `.ai_orchestration_protocol.md` Sección 4.

**Versión Log**: v4.19.0-beta
**Última Actualización**: 14 de Abril, 2026 (ETI-SRE-DB-BACKPRESSURE-CHAIN-2026-04-14 completado)

---

## 📈 ÉPICAS ESTRATÉGICAS

> ℹ️ Solo se muestran Épicas en estado `ACTIVA` o `PENDIENTE`. Las Épicas `COMPLETADA` se archivan en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS) y se eliminan de este documento.

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
