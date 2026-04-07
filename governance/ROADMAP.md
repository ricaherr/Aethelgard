# AETHELGARD: ESTRATEGIC ROADMAP

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Visión estratégica de alto nivel. No es un diario de tareas.
> - **Estructura**: Épicas (`E1, E2...`) con su estado y el Sprint que las ejecuta. Sin checkboxes de subtareas.
> - **Estados de Épica**: `PENDIENTE` · `ACTIVA` · `COMPLETADA`
> - **Al iniciar implementación**: Marcar Épica como `ACTIVA` ANTES de escribir una línea de código.
> - **Al completar Sprint**: Actualizar Épica a `COMPLETADA` + archivar en [docs/SYSTEM_LEDGER.md](SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS, formato ÉPICA-ARCHIVO) + **ELIMINAR la Épica del ROADMAP**.
> - **NO agregar aquí**: listas de archivos modificados, métricas de tests, detalles de implementación (eso va en SPRINT.md).
> - **Framework completo**: `.ai_orchestration_protocol.md` Sección 4.

**Versión Log**: v4.18.0-beta
**Última Actualización**: 6 de Abril, 2026 (Plan E15 activado · Sprint 26 en preparación)

---

## 📈 ÉPICAS ESTRATÉGICAS

> ℹ️ Solo se muestran Épicas en estado `ACTIVA` o `PENDIENTE`. Las Épicas `COMPLETADA` se archivan en [docs/SYSTEM_LEDGER.md](SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS) y se eliminan de este documento.

### E5: Interfaz Fractal & Experiencia Futurista (Dominio 09) — ACTIVA
**Sprint**: 25 | **Trace_ID**: UI-V3-FRACTAL-FUTURE-2026
**Objetivo**: Evolucionar la terminal a una consola de alta densidad de información con navegación fractal y elementos de manipulación directa.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 9.4 | Unified Telemetry Stream (The Synapse) | 09 | 25 | [DONE] |
| HU 9.5 | Fractal Zoom Engine | 09 | — | [TODO] |
| HU 9.6 | Direct Manipulation (Drag & Drop) | 09 | — | [TODO] |
| HU 9.7 | Sci-Fi Component Library (HUDs) | 09 | — | [TODO] |
| HU 9.8 | Event Soldering (ANOMALY + REASONING) | 09 | — | [TODO] |

### E15: Persistencia Agnóstica & Telemetría Broker-Neutral (Dominios 08 + 10) — ACTIVA
**Sprint**: 26 | **Trace_ID**: ARCH-DB-DRIVER-AGNOSTIC-MT5-DECOUPLING-2026-04-06
**Objetivo**: Eliminar acoplamiento operativo a MT5 en salud/telemetría y preparar la capa de persistencia para motores SQL robustos sin embudo global en el Core.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 10.20 | Telemetría agnóstica de proveedor (sin dependencia MT5 hardcoded) | 10 | 26 | [DONE] |
| HU 8.2 | Contrato de Persistencia Agnóstica (IDatabaseDriver + adapters) | 08 | 26 | [DONE] |
| HU 8.3 | Concurrencia SQLite híbrida (retry/backoff + cola selectiva) | 08 | 26 | [TODO] |

> [!NOTE]
> El historial completo de épicas completadas se encuentra en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md).
> El protocolo y último informe de auditoría están en [AUDIT_PROTOCOL.md](AUDIT_PROTOCOL.md) y [AUDITORIA_ESTADO_REAL.md](AUDITORIA_ESTADO_REAL.md).
