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

### E10: Motor de Backtesting Inteligente — EDGE Evaluation Framework — ACTIVA
**Sprint**: 9 | **Trace_ID**: EDGE-BACKTEST-EVAL-FRAMEWORK-2026-03-24
**Objetivo**: Refundar el motor de backtesting desde sus fundamentos: reemplazar la simulación momentum genérica por ejecución real de la lógica de cada estrategia; introducir evaluación multi-par y multi-timeframe con descubrimiento empírico (sin suposiciones a priori); eliminar datos sintéticos del path de producción mediante cadena de fallback multi-proveedor; implementar scoring con confianza estadística continua `n/(n+k)`; y desplegar un gestor adaptativo de recursos que suspende componentes ociosos, dinamiza el cooldown según contexto operacional y protege la integridad del servidor.

| HU | Nombre | Dominio | Sprint | Estado |
|---|---|---|---|---|
| HU 7.6  | Interfaz estándar de evaluación histórica en estrategias | 07 | 9 | [TODO] |
| HU 7.7  | Simulación real por estrategia — despacho a lógica propia | 07 | 9 | [TODO] |
| HU 7.8  | Contexto estructural declarado en sys_strategies | 07 | 9 | [TODO] |
| HU 7.9  | Evaluación multi-timeframe con round-robin y pre-filtro | 07 | — | |
| HU 7.10 | RegimeClassifier real en pipeline de backtesting | 07 | — | |
| HU 7.11 | Cadena de fallback multi-proveedor — eliminar síntesis | 07 | 9 | [TODO] |
| HU 10.7 | Adaptive Operational Mode Manager | 10 | 9 | [TODO] |
| HU 7.12 | Adaptive Backtest Scheduler — cooldown dinámico y queue de prioridad | 07 | — | |
| HU 7.13 | Rediseño semántico de affinity_scores | 07 | — | |
| HU 7.14 | Backtesting multi-par secuencial | 07 | — | |
| HU 7.15 | Score con confianza estadística n/(n+k) | 07 | — | |
| HU 7.16 | Filtro de compatibilidad de régimen pre-evaluación | 07 | — | |
| HU 7.17 | Tabla sys_strategy_pair_coverage | 07 | — | |
| HU 7.18 | Scheduler inteligente de backtests — prioritized queue | 07 | — | |
| HU 7.19 | Detector de overfitting por par | 07 | — | |

**Dependencias entre HUs**:
```
HU 7.6 → HU 7.7
HU 7.8 → HU 7.9 → HU 7.16
HU 7.10 (independiente — mejora clasificación de régimen)
HU 7.11 (independiente — política de datos)
HU 10.7 → HU 7.12 (scheduler requiere gestor de modos)
HU 7.6 + HU 7.7 + HU 7.8 + HU 7.9 + HU 7.10 + HU 7.11 + HU 10.7 + HU 7.12
    → HU 7.13 → HU 7.14 → HU 7.15
                HU 7.16 (paralelo a HU 7.14)
    → HU 7.17 → HU 7.18 → HU 7.19
```
**Sprint mínimo viable**: HU 7.6 + HU 7.7 + HU 7.8 + HU 10.7 + HU 7.11 — scores con lógica real, servidor protegido, sin datos sintéticos.

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

