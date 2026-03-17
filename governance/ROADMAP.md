# AETHELGARD: ESTRATEGIC ROADMAP

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Visión estratégica de alto nivel. No es un diario de tareas.
> - **Estructura**: Épicas (`E1, E2...`) con su estado y el Sprint que las ejecuta. Sin checkboxes de subtareas.
> - **Estados de Épica**: `PENDIENTE` · `ACTIVA` · `COMPLETADA`
> - **Al iniciar implementación**: Marcar Épica como `ACTIVA` ANTES de escribir una línea de código.
> - **Al completar Sprint**: Actualizar Épica a `COMPLETADA` + archivar en [docs/SYSTEM_LEDGER.md](../docs/SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS, formato ÉPICA-ARCHIVO) + **ELIMINAR la Épica del ROADMAP**.
> - **NO agregar aquí**: listas de archivos modificados, métricas de tests, detalles de implementación (eso va en SPRINT.md).
> - **Framework completo**: `.ai_orchestration_protocol.md` Sección 4.

**Versión Log**: v4.3.2-beta
**Última Actualización**: 15 de Marzo, 2026

---

## 📈 ÉPICAS ESTRATÉGICAS

> ℹ️ Solo se muestran Épicas en estado `ACTIVA` o `PENDIENTE`. Las Épicas `COMPLETADA` se archivan en [docs/SYSTEM_LEDGER.md](../docs/SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS) y se eliminan de este documento.

### E4: Expansión Institucional & Conectividad Nivel 2 (Dominios 01, 03, 05) — ACTIVA
**Sprints**: Sprint N2 | **Trace_ID**: pendiente
**Objetivo**: FIX API para Prime Brokers + WebSocket Auth estandarizado + JSON_SCHEMA Interpreter.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 5.1 | Capa Institutional FIX API (Prime Brokers) | 05 | Sprint N2 | [TODO] |
| HU 5.2 | Adaptive Slippage Controller | 05 | Sprint N2 | [DONE] |
| N2-1 | JSON_SCHEMA Interpreter | 03 | Sprint N2 | [DONE] |
| N2-2 | WebSocket Auth Standardization | 01 | Sprint N2 | [DONE] |

---

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
> El historial completo de V1, V2 y Auditoría ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).

