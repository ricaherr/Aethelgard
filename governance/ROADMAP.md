# AETHELGARD: ESTRATEGIC ROADMAP

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Visión estratégica de alto nivel. No es un diario de tareas.
> - **Estructura**: Épicas (`E1, E2...`) con su estado y el Sprint que las ejecuta. Sin checkboxes de subtareas.
> - **Estados de Épica**: `PENDIENTE` · `ACTIVA` · `COMPLETADA`
> - **Al iniciar implementación**: Marcar Épica como `ACTIVA` ANTES de escribir una línea de código.
> - **Al completar Sprint**: Actualizar Épica a `COMPLETADA` + archivar en [docs/SYSTEM_LEDGER.md](SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS, formato ÉPICA-ARCHIVO) + **ELIMINAR la Épica del ROADMAP**.
> - **NO agregar aquí**: listas de archivos modificados, métricas de tests, detalles de implementación (eso va en SPRINT.md).
> - **Framework completo**: `.ai_orchestration_protocol.md` Sección 4.

**Versión Log**: v4.6.0-beta
**Última Actualización**: 23 de Marzo, 2026

---

## 📈 ÉPICAS ESTRATÉGICAS

> ℹ️ Solo se muestran Épicas en estado `ACTIVA` o `PENDIENTE`. Las Épicas `COMPLETADA` se archivan en [docs/SYSTEM_LEDGER.md](SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS) y se eliminan de este documento.

### E9: Desbloqueo Operacional del Pipeline — ACTIVA
**Sprint**: 8 | **Trace_ID**: PIPELINE-UNBLOCK-EDGE-2026-03-24
**Objetivo**: Resolver 5 bloqueos operacionales críticos que impiden el flujo BACKTEST→SHADOW→LIVE y elevar la resiliencia del sistema: filtro de activos incorrecto en SignalFactory, cooldown de backtest mal implementado (last_backtest_at), EdgeMonitor hardcodeado a MT5, capital hardcodeado, y ausencia de protección contra instancias duplicadas. Documentar el diseño del AutonomousSystemOrchestrator (FASE4) en governance.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 10.3 | Proceso Singleton — PID Lockfile | 10 | 8 | [TODO] |
| HU 10.4 | Capital Dinámico desde sys_config | 10 | 8 | [TODO] |
| HU 7.5 | Backtest Cooldown — last_backtest_at | 07 | 8 | [TODO] |
| HU 3.9 | Signal Factory — InstrumentManager Filter | 03 | 8 | [TODO] |
| HU 10.5 | EdgeMonitor Connector-Agnóstico | 10 | 8 | [TODO] |
| HU 10.6 | AutonomousSystemOrchestrator — Diseño FASE4 | 10 | 8 | [TODO] |

### E5: Interfaz Fractal & Experiencia Futurista (Dominio 09) — PENDIENTE
**Sprint**: por definir | **Trace_ID**: UI-V3-FRACTAL-FUTURE-2026
**Objetivo**: Evolucionar la terminal a una consola de alta densidad de información con navegación fractal y elementos de manipulación directa.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 9.4 | Unified Telemetry Stream (The Synapse) | 09 | — | [TODO] |
| HU 9.5 | Fractal Zoom Engine | 09 | — | [TODO] |
| HU 9.6 | Direct Manipulation (Drag & Drop) | 09 | — | [TODO] |
| HU 9.7 | Sci-Fi Component Library (HUDs) | 09 | — | [TODO] |
| HU 9.8 | Event Soldering (ANOMALY + REASONING) | 09 | — | [TODO] |

> [!NOTE]
> El historial completo de épicas completadas se encuentra en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md).
> El protocolo y último informe de auditoría están en [AUDIT_PROTOCOL.md](AUDIT_PROTOCOL.md) y [AUDITORIA_ESTADO_REAL.md](AUDITORIA_ESTADO_REAL.md).

