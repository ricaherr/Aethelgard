# AETHELGARD MANIFESTO

## Archivo de Verdad: Arquitectura Basada en Pilares Consolidados

**Status**: 🚀 ACTIVO

---

## I. Declaración de Intenciones (Filosofía Aethelgard)

Aethelgard es un ecosistema autónomo, proactivo y matemáticamente agnóstico de trading institucional.

---

## I.A Contrato Arquitectónico: DB como SSOT + Snapshot en Memoria

**Vigente desde:** 2026-04-13 | Trace_ID: EDGE-STRATEGY-SSOT-SYNC-2026-04-13

### Regla de Oro: Metadata Estratégica

Toda metadata operativa de una estrategia (`affinity_scores`, `market_whitelist`, `execution_params`) reside exclusivamente en `sys_strategies` (SSOT). Las estrategias PYTHON_CLASS **no pueden usar constantes de clase hardcodeadas como fuente de filtrado operativo**.

### Contrato de Runtime

| Capa | Rol | Fuente de datos |
|---|---|---|
| `sys_strategies` | Fuente única de verdad | SQLite — DB |
| `StrategyEngineFactory._inject_metadata_snapshot()` | Carga snapshot al instanciar | Lee `sys_strategies` en startup |
| `strategy._affinity_scores` / `_market_whitelist` | Runtime operativo | Snapshot en memoria (inmutable por ciclo) |
| `StrategyGatekeeper` | Pre-tick post-análisis | `usr_strategy_logs` (scores aprendidos) |

### Prohibición Explícita

Las clases PYTHON_CLASS (`MOM_BIAS_0001`, `LIQ_SWEEP_0001`, `STRUC_SHIFT_0001`, etc.) **no deben usar `self.AFFINITY_SCORES` ni `self.MARKET_WHITELIST` como fuente operativa de filtrado**. Esas constantes de clase existen únicamente como documentación semántica y fallback de compatibilidad regresiva para entornos sin factory.

### Refresh Controlado

El snapshot se carga **una sola vez por startup** (compilación única). Si `sys_strategies` cambia en DB, la estrategia toma el nuevo valor en el **siguiente reinicio del motor**, no en el siguiente tick. No se realizan lecturas a DB durante `analyze()`.

### Trazabilidad de No-Señal

Cuando `analyze()` retorna `None`, el motivo debe quedar diferenciado en logs:
- `symbol_not_in_affinity` → símbolo no en snapshot
- `affinity_below_threshold` → score insuficiente
- `symbol_not_in_market_whitelist` → whitelist activa lo excluye
- `insuficiente` / `insufficient` → datos OHLC insuficientes

---

## II. Mapa de los 5 Pilares (Dominios Consolidados)

| Dominio | Descripción | Documento |
|---|---|---|
| **01. CORE ADAPTIVE BRAIN** | Inteligencia, regímenes y generación de Alpha. | [01_CORE_ADAPTIVE_BRAIN.md](01_CORE_ADAPTIVE_BRAIN.md) |
| **02. EXECUTOR GOVERNANCE** | Gestión de riesgo unificada y protocolos Anomaly Sentinel. | [02_EXECUTOR_GOVERNANCE.md](02_EXECUTOR_GOVERNANCE.md) |
| **03. PERFORMANCE DARWINISM** | Inteligencia de Portafolio cruzada con Coherencia Técnica. | [03_PERFORMANCE_DARWINISM.md](03_PERFORMANCE_DARWINISM.md) |
| **04. DATA SOVEREIGNTY INFRA** | Control SSOT, separación de tenants/esquemas. | [04_DATA_SOVEREIGNTY_INFRA.md](04_DATA_SOVEREIGNTY_INFRA.md) |
| **05. IDENTITY SECURITY** | Protección de sesiones y aislamiento multi-tenant. | [05_IDENTITY_SECURITY.md](05_IDENTITY_SECURITY.md) |

---

## III. Capa de Interfaz Institucional (Contrato de Visualización)

El ecosistema expone su cerebro y métricas a través de una "Intelligence Terminal" densa, alimentada por eventos de WebSocket en tiempo real. 

### Arquitectura de Navegación Fractal (Las 7 Páginas)

1. **TRADER**: El epicentro. Consume estado de mercado vía WebSocket, mostrando señales activas, bias global.
2. **ANÁLISIS**: Muestra matrices de correlación y visualización técnica de componentes como FVG. 
3. **PORTFOLIO**: Presenta la exposición consolidada, tickets activos por tenant.
4. **EDGE**: Permite observar el `EdgeTuner` interactuando y ver cómo los pesos algorítmicos se recalculan.
5. **SATELLITE LINK**: Centro de operaciones de conectividad (MT5, FIX, cTrader).
6. **MONITOR**: Audita recursos técnicos. Rastrea carga de CPU, la fidelidad de base de datos Multi-tenant.
7. **SETTINGS**: Configuración integral de símbolos, notificaciones por Telegram, RBAC y Auto-Trading globales.
