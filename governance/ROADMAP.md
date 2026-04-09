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
**Última Actualización**: 7 de Abril, 2026 (E15 completada y archivada)

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

### E17: Data Sovereignty Enforcement Root-Fix — ACTIVA
**Sprint**: 27 | **Trace_ID**: DB-POLICY-ROOT-LOCK-2026-04-07
**Objetivo**: Ejecutar la política integral de gestión de datos por fases, iniciando con enforcement para congelar deuda de persistencia y eliminar bypass de contrato de driver.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 8.4 | Enforcement de Persistencia (guard + auditoría AST + baseline 99 violaciones) | 08 | 27 | [DONE] |
| HU 8.5 | Migración de Writes Bypass a Contrato de Driver (market_db + storage) | 08 | 27 | [DONE] |
| HU 8.6 | Migración de Writes Legacy SystemMixin (13 métodos → transaction contract, baseline 90→76) | 08 | 27 | [DONE] |
| HU 8.7 | Eliminación de Doble-Commit en callbacks serializados (signals/execution/broker + tx_lock cleanup, baseline 76→66) | 08 | 27 | [DONE] |
| HU 10.21 | Hardening de Arranque y Señales de Consola (sin ruido/errores espurios) | 10 | 27 | [DONE] |
| HU 10.22 | Grace Window OEM para invariantes de bootstrap (shadow_sync/lifecycle_coherence FAIL->WARN en arranque) | 10 | 27 | [DONE] |
| HU 10.23 | Hardening OEM post-bootstrap (separación accionable vs no-accionable en shadow_sync/lifecycle_coherence) | 10 | 27 | [DONE] |

> [!NOTE]
> El historial completo de épicas completadas se encuentra en [SYSTEM_LEDGER.md](SYSTEM_LEDGER.md).
> El protocolo y último informe de auditoría están en [AUDIT_PROTOCOL.md](AUDIT_PROTOCOL.md) y [AUDITORIA_ESTADO_REAL.md](AUDITORIA_ESTADO_REAL.md).
