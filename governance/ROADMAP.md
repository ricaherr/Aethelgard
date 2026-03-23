# AETHELGARD: ESTRATEGIC ROADMAP

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Visión estratégica de alto nivel. No es un diario de tareas.
> - **Estructura**: Épicas (`E1, E2...`) con su estado y el Sprint que las ejecuta. Sin checkboxes de subtareas.
> - **Estados de Épica**: `PENDIENTE` · `ACTIVA` · `COMPLETADA`
> - **Al iniciar implementación**: Marcar Épica como `ACTIVA` ANTES de escribir una línea de código.
> - **Al completar Sprint**: Actualizar Épica a `COMPLETADA` + archivar en [docs/SYSTEM_LEDGER.md](../docs/SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS, formato ÉPICA-ARCHIVO) + **ELIMINAR la Épica del ROADMAP**.
> - **NO agregar aquí**: listas de archivos modificados, métricas de tests, detalles de implementación (eso va en SPRINT.md).
> - **Framework completo**: `.ai_orchestration_protocol.md` Sección 4.

**Versión Log**: v4.5.0-beta
**Última Actualización**: 21 de Marzo, 2026

---

## 📈 ÉPICAS ESTRATÉGICAS

> ℹ️ Solo se muestran Épicas en estado `ACTIVA` o `PENDIENTE`. Las Épicas `COMPLETADA` se archivan en [docs/SYSTEM_LEDGER.md](../docs/SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS) y se eliminan de este documento.

### E7: cTrader WebSocket Data Protocol — COMPLETADA
**Sprint**: 5 | **Trace_ID**: CTRADER-WS-PROTO-2026-03-21
**Objetivo**: Completar el conector cTrader como proveedor de datos primario FOREX. Implementar el protocolo WebSocket protobuf (Spotware Open API) para obtener OHLC bars reales. Corregir los endpoints REST de ejecución usando `api.spotware.com` con `oauth_token`. El conector debe ser la única fuente de datos FOREX del sistema sin depender de Yahoo como fallback.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| N1-7 | cTrader WebSocket Protocol — OHLC via Protobuf | 00_INFRA / 05_EXEC | 5 | [DONE] |

---

### E6: Purga de DB Legacy & SSOT Enforcement (Dominio 00_INFRA) — ACTIVA
**Sprint**: 4 | **Trace_ID**: DB-LEGACY-PURGE-2026-03-21
**Objetivo**: Eliminar `data_vault/aethelgard.db` (legacy) y toda referencia hardcodeada a su ruta. La única BD global del sistema debe ser `data_vault/global/aethelgard.db`.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| N0-5 | Legacy DB Purge & SSOT Enforcement | 00_INFRA | 4 | [DONE] |

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

