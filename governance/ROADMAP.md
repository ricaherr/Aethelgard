# AETHELGARD: ESTRATEGIC ROADMAP

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Visión estratégica de alto nivel. No es un diario de tareas.
> - **Estructura**: Épicas (`E1, E2...`) con su estado y el Sprint que las ejecuta. Sin checkboxes de subtareas.
> - **Estados de Épica**: `PENDIENTE` · `ACTIVA` · `COMPLETADA`
> - **Al iniciar implementación**: Marcar Épica como `ACTIVA` ANTES de escribir una línea de código.
> - **Al completar Sprint**: Actualizar Épica a `COMPLETADA` + archivar en [docs/SYSTEM_LEDGER.md](SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS, formato ÉPICA-ARCHIVO) + **ELIMINAR la Épica del ROADMAP**.
> - **NO agregar aquí**: listas de archivos modificados, métricas de tests, detalles de implementación (eso va en SPRINT.md).
> - **Framework completo**: `.ai_orchestration_protocol.md` Sección 4.

**Versión Log**: v4.17.0-beta
**Última Actualización**: 27 de Marzo, 2026 (Sprint 23 iniciado)

---

## 📈 ÉPICAS ESTRATÉGICAS

> ℹ️ Solo se muestran Épicas en estado `ACTIVA` o `PENDIENTE`. Las Épicas `COMPLETADA` se archivan en [docs/SYSTEM_LEDGER.md](SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS) y se eliminan de este documento.

### E13: EDGE Reliability — Certeza de Componentes & Auto-Auditoría (Dominio 10) — ACTIVA
**Sprint**: 23 | **Trace_ID**: EDGE-RELIABILITY-SELF-AUDIT-2026
**Objetivo**: Garantizar que cada componente del sistema funciona correctamente — código correcto, implementación correcta, diseño correcto y lógica financiera correcta — mediante dos mecanismos complementarios: (1) activar el `OperationalEdgeMonitor` como motor de auto-auditoría en tiempo real, y (2) establecer tests de contrato que conviertan cada bug conocido en una red de seguridad permanente contra regresiones.

**Motivación**: Las auditorías manuales son fotografías estáticas de un sistema dinámico. Cada fix puede introducir un nuevo bug sin que ningún mecanismo lo detecte. El sistema ya tiene el OEM diseñado para auto-auditarse, pero no está integrado en producción. El objetivo no es hacer más auditorías — es que el sistema se audite solo.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 10.10 | OEM Production Integration | 10 | 23 | [TODO] |
| HU 10.11 | OEM Loop Heartbeat Check | 10 | 23 | [TODO] |
| HU 10.12 | Timeout Guards en run_single_cycle | 10 | 23 | [TODO] |
| HU 10.13 | Contract Tests — Bugs Conocidos | 10 | 23 | [TODO] |

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
> El historial completo de épicas completadas se encuentra en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md).
> El protocolo y último informe de auditoría están en [AUDIT_PROTOCOL.md](AUDIT_PROTOCOL.md) y [AUDITORIA_ESTADO_REAL.md](AUDITORIA_ESTADO_REAL.md).

