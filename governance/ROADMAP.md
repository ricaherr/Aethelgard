# AETHELGARD: ESTRATEGIC ROADMAP

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Visión estratégica de alto nivel. No es un diario de tareas.
> - **Estructura**: Épicas (`E1, E2...`) con su estado y el Sprint que las ejecuta. Sin checkboxes de subtareas.
> - **Estados de Épica**: `PENDIENTE` · `ACTIVA` · `COMPLETADA`
> - **Al iniciar implementación**: Marcar Épica como `ACTIVA` ANTES de escribir una línea de código.
> - **Al completar Sprint**: Actualizar Épica a `COMPLETADA` + archivar en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS, formato ÉPICA-ARCHIVO) + **ELIMINAR la Épica del ROADMAP**.
> - **NO agregar aquí**: listas de archivos modificados, métricas de tests, detalles de implementación (eso va en SPRINT.md).
> - **Framework completo**: `.ai_orchestration_protocol.md` Sección 4.

**Versión Log**: v4.18.0-beta
**Última Actualización**: 8 de Abril, 2026 (E17 completada y archivada)

---

## 📈 ÉPICAS ESTRATÉGICAS

> ℹ️ Solo se muestran Épicas en estado `ACTIVA` o `PENDIENTE`. Las Épicas `COMPLETADA` se archivan en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md) (sección ÉPICAS ARCHIVADAS) y se eliminan de este documento.

### E18: SRE — Reparación y Estabilización Operacional — ACTIVA
**Sprint**: 28 | **Trace_ID**: E18-SRE-OPERATIONAL-REPAIR-2026-04-09
**Objetivo**: Reparar el pipeline de señales bloqueado por deriva SSOT entre `sys_strategies.mode` y `sys_signal_ranking.execution_mode`, restaurar Shadow trading, corregir bugs silenciados y establecer observabilidad SRE mínima viable.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 8.8 | SSOT Execution Mode Drift Fix | 08 | 28 | [DONE] |
| HU 10.24 | Shadow Pool Bootstrap Diagnostics | 10 | 28 | [TODO] |
| HU 10.25 | Health Endpoint SRE | 10 | 28 | [DONE] |
| HU 10.26 | Heartbeat Audit Trail Repair | 10 | 28 | [DONE] |
| HU 9.9 | UI Confidence Display Overflow Fix | 09 | 28 | [TODO] |

---

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

---

### E16: Membresía SaaS, Correlación Multi-Mercado & Darwinismo de Portafolio — ACTIVA
**Sprint**: 27 | **Trace_ID**: E16-SAAS-PORTFOLIO-DARWIN-2026
**Objetivo**: Completar la jerarquía de acceso SaaS (3 tiers), implementar correlación inter-mercado para señales de alta fidelidad, el motor Shadow Reality con penalización real y el ranking darwinista de estrategias por usuario.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 1.3 | User Role & Membership Level (Deuda Técnica) | 01 | 27 | [TODO] |
| HU 3.3 | Multi-Market Alpha Correlator | 03 | 27 | [TODO] |
| HU 6.1 | Shadow Reality Engine (Penalty Injector) | 06 | 27 | [TODO] |
| HU 6.2 | Multi-Tenant Strategy Ranker | 06 | 27 | [TODO] |

---

> [!NOTE]
> El historial completo de épicas completadas se encuentra en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md).
> El protocolo y último informe de auditoría están en [AUDIT_PROTOCOL.md](AUDIT_PROTOCOL.md) y [AUDITORIA_ESTADO_REAL.md](AUDITORIA_ESTADO_REAL.md).
