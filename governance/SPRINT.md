# AETHELGARD: SPRINT LOG

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Diario de ejecución. Cada Sprint referencia una Épica del ROADMAP y las HUs del BACKLOG que ejecuta.
> - **Estructura**: `Sprint NNN: [nombre]` → tareas con referencia `HU X.Y` → snapshot de cierre.
> - **Estados únicos permitidos**: `[TODO]` · `[DEV]` · `[DONE]`
> - **`[DONE]`** solo si `validate_all.py` ✅ 100% ejecutado y pasado.
> - **Al cerrar Sprint**: snapshot de métricas + actualizar HUs en BACKLOG a `[DONE]` + archivar en SYSTEM_LEDGER.
> - **PROHIBIDO**: `[x]`, `[QA]`, `[IN_PROGRESS]`, `[CERRADO]`, `[ACTIVO]`, `✅ COMPLETADA`
> - **Framework completo**: `.ai_orchestration_protocol.md` Sección 4.

---

# SPRINT 2: SUPREMACÍA DE EJECUCIÓN (Risk Governance) — [DONE]

**Inicio**: 27 de Febrero, 2026  
**Fin**: 28 de Febrero, 2026  
**Objetivo**: Establecer el sistema nervioso central de gestión de riesgo institucional (Dominio 04) y asegurar la integridad del entorno base.  
**Versión Target**: v4.0.0-beta.1  
**Estado Final**: ✅ COMPLETADO | 6/6 tareas DONE | Cero regresiones (61/61 tests PASSED)

---

## 📋 Tareas del Sprint

- [DONE] **Path Resilience (HU 10.2)**
  - Script agnóstico `validate_env.py` para verificar salud de infraestructura.
  - Validación de rutas, dependencias, variables de entorno y versiones de Python.

- [DONE] **Safety Governor & Sovereignty Gateway (HU 4.4)**
  - TDD implementado (`test_safety_governor.py`).
  - Lógica de Unidades R implementada en `RiskManager.can_take_new_trade()`.
  - Veto granular para proteger el capital institucional (`max_r_per_trade`).
  - Generación de `RejectionAudit` ante vetos.
  - Endpoint de dry-run validation expuesto en `/api/risk/validate`.

- [DONE] **Exposure & Drawdown Monitor Multi-Tenant (HU 4.5)**
  - TDD implementado (`test_drawdown_monitor.py`).
  - Monitoreo en tiempo real de picos de equidad y umbrales de Drawdown (Soft/Hard).
  - Aislamiento arquitectónico garantizado por Tenant_ID.
  - Endpoint de monitoreo expuesto en `/api/risk/exposure`.

- [DONE] **Institutional Footprint Core (HU 3.2)**
  - Creado `LiquidityService` con detección de FVG y Order Blocks.
  - Integrado en `RiskManager.can_take_new_trade` mediante `[CONTEXT_WARNING]`.
  - TDD implementado (`test_liquidity_service.py`).

- [DONE] **Sentiment Stream Integration (HU 3.4 - E3)**
  - Creado `core_brain/services/sentiment_service.py` con enfoque API-first y fallback heurístico institucional.
  - Integrado veto macro en `RiskManager.can_take_new_trade` mediante `[SENTIMENT_VETO]`.
  - Snapshot de sesgo macro persistido en `signal.metadata["institutional_sentiment"]`.

- [DONE] **Depredación de Contexto / Predator Sense (HU 2.2 - E3)**
  - Extendido `ConfluenceService` con detección de barrido de liquidez inter-mercado (`detect_predator_divergence`).
  - Expuesto endpoint operativo `/api/analysis/predator-radar`.
  - UI: widget `Predator Radar` en `AnalysisPage` para monitoreo de `divergence_strength` en tiempo real.

---

## 📸 Snapshot de Contexto

| Métrica | Valor |
|---|---|
| **Estado de Riesgo** | Gobernanza R-Unit Activa y Drawdown Controlado |
| **Resiliencia de Entorno** | Verificada (100% path agnostic) |
| **Integridad TDD** | 61/61 tests PASSED (Cero Regresiones) |
| **Arquitectura** | SSOT (Unica DB), Endpoints Aislados |
| **Versión Global** | v4.0.0-beta.1 |

---

# SPRINT 3: COHERENCIA FRACTAL & ADAPTABILIDAD (Dominio Sensorial)

**Inicio**: 1 de Marzo, 2026  
**Objetivo**: Establecer la supremacía analítica mediante detección de anomalías, meta-coherencia de modelos y auto-calibración adaptativa.  
**Versión Target**: v4.1.0-beta.3  
**Dominios**: 02, 03, 06, 07, 10  
**Estado**: [DONE]

---

## 📋 Tareas del Sprint 3

- [DONE] **Multi-Scale Regime Vectorizer (HU 2.1)**
  - ✅ Unificación de temporalidades para decisión coherente.
  - ✅ Motor RegimeService con lectura de M15, H1, H4.
  - ✅ Regla de Veto Fractal (H4=BEAR + M15=BULL → RETRACEMENT_RISK).
  - ✅ Widget "Fractal Context Manager" en UI.
  - ✅ Sincronización de Ledger (SSOT).
  - ✅ 15/15 Tests PASSED.

- [TODO] **Depredación de Contexto / Predator Sense Optimization (HU 2.2 - Extensión)**
  - Optimización del scanner `detect_predator_divergence` con métricas de predicción.
  - Validación cruzada inter-mercado para alta fidelidad.

- [DONE] **Anomaly Sentinel - Detección de Cisnes Negros (HU 4.6)**
  - ✅ Monitor de eventos de baja probabilidad (volatilidad extrema) con Z-Score > 3.0
  - ✅ Flash Crash Detector (caída > -2% en 1 vela)
  - ✅ Protocolo defensivo: Lockdown Preventivo + Cancel Orders + SL->Breakeven
  - ✅ Persistencia en DB (anomaly_events table) con Trace_ID
  - ✅ Broadcast [ANOMALY_DETECTED] vía WebSocket
  - ✅ Thought Console endpoints (6 routers) + sugerencias inteligentes
  - ✅ Integración con Health System (modo NORMAL/CAUTION/DEGRADED/STRESSED)
  - ✅ 21/21 Tests PASSED | validate_all.py: 100% OK

- [DONE] **Coherence Drift Monitoring (HU 6.3)**
  - Algoritmo de divergencia: modelo esperado vs ejecución en vivo.
  - Alerta temprana de deriva técnica.

- [DONE] **Asset Efficiency Score Gatekeeper (HU 7.2)**
  - ✅ Tabla `strategies` con campos class_id, mnemonic, affinity_scores (JSON), market_whitelist
  - ✅ Tabla `strategy_performance_logs` para logging relacional de desempeño por activo
  - ✅ StrategyGatekeeper: componente en-memory ultra-rápido (< 1ms latencia)
  - ✅ Validación pre-tick: `can_execute_on_tick()` verifica score >= min_threshold
  - ✅ Abort execution automático si asset no cumple (veto)
  - ✅ Market whitelist enforcement: control de activos permitidos
  - ✅ Learning integration: `log_asset_performance()` → strategy_performance_logs
  - ✅ Cálculo dinámico: `calculate_asset_affinity_score()` con ponderación (0.5 win_rate, 0.3 pf_score, 0.2 momentum)
  - ✅ Refresh en-memory: `refresh_affinity_scores()` sincroniza con DB
  - ✅ 17/17 Tests PASSED | validate_all.py: 14/14 modules PASSED
  - ✅ Documentación completa en AETHELGARD_MANIFESTO.md (Sección VI)
  - Trace_ID: EXEC-EFFICIENCY-SCORE-001

- [TODO] **Confidence Threshold Adaptive (HU 7.1)**

- [TODO] **Autonomous Heartbeat & Self-Healing (HU 10.1)**
  - Monitoreo vital continuo (CPU, memoria, conectividad).
  - Auto-recuperación de servicios degradados.

---

## 📸 Snapshot Sprint 3 (Progreso: 2/6 - HU 2.1 + HU 4.6)

| Métrica | Valor |
|---|---|
| **Arquitectura Base** | v4.0.0-beta.1 (18 módulos core + 9 servicios) |
| **Versión Target** | v4.1.0-beta.3 |
| **HU 2.1 Status** | ✅ COMPLETADA (RegimeService, FractalContext, Tests 15/15) |
| **HU 4.6 Status** | ✅ COMPLETADA (AnomalyService, 6 API endpoints, Tests 21/21) |
| **Validación Sistema** | ✅ 14/14 PASSED (validate_all.py) |
| **Total Tests** | 82/82 PASSED (Cero deuda, sin regresiones) |
| **Épica Activa** | E3: Dominio Sensorial & Adaptabilidad |
| **Última Actualización** | 1 de Marzo, 2026 - 20:45 UTC

---

# SPRINT 4: INTEGRACIÓN SENSORIAL Y ORQUESTACIÓN — [DONE]

**Inicio**: 2 de Marzo, 2026  
**Objetivo**: Integrar la capa sensorial completa con orquestación centralizada y expandir capacidades de usuario hacia empoderamiento operativo.  
**Versión Target**: v4.2.0-beta.1  
**Dominios**: 02, 03, 05, 06, 09  
**Estado**: [DONE]

---

## 📋 Tareas del Sprint 4

- [DONE] **Market Structure Analyzer Sensorial (HU 3.3)** (DOC-STRUC-SHIFT-2026)
  - ✅ Sensor de detección HH/HL/LH/LL con caching optimizado
  - ✅ Breaker Block mapping y Break of Structure (BOS) detection
  - ✅ Pullback zone calculation con tolerancia configurable
  - ✅ 14/14 Tests PASSED | Integración en StructureShift0001Strategy

- [DONE] **Orquestación Conflict Resolver (HU 5.2, 6.2)** (EXEC-ORCHESTRA-001)
  - ✅ ConflictResolver: Resolución automática de conflictos multi-estrategia
  - ✅ Jerarquía de prioridades: FundamentalGuard → Asset Affinity → Régimen Alignment
  - ✅ Risk Scaling dinámico según régimen (1.0× a 0.5×)

- [DONE] **UI Mapping Service & Terminal 2.0 (HU 9.1, 9.2)** (EXEC-ORCHESTRA-001)
  - ✅ UIDrawingFactory con paleta Bloomberg Dark (16 colores)
  - ✅ Sistema de 6 capas (Layers): Structure, Targets, Liquidity, MovingAverages, RiskZones, Labels
  - ✅ Elemento visual base (DrawingElement) con z-index automático
  - ✅ Emisión en tiempo real vía WebSocket a UI

- [DONE] **Strategy Heartbeat Monitor (HU 10.1)** (EXEC-ORCHESTRA-001)
  - ✅ StrategyHeartbeat: Monitoreo individual de 6 estrategias (IDLE, SCANNING, POSITION_ACTIVE, etc)
  - ✅ SystemHealthReporter: Health Score integral (CPU, Memory, Conectividad, Estrategias)
  - ✅ Persistencia en BD cada 10 segundos

- [TODO] **E5: User Empowerment (HU 9.3 - 🔴 BLOQUEADO)**
  - ✅ Backend: Manual de Usuario Interactivo (estructurado)
  - ✅ Backend: Sistema de Ayuda Contextual en JSON (description fields)
  - ✅ Backend: Monitoreo de Salud (Heartbeat integrado)
  - ❌ Frontend: Auditoría de Presentación (React renderization failing)
  - 🔴 **BLOQUEADO HASTA**: Validación visual real de WebSocket messages en componentes React
  - **Próximos Pasos**: Auditoría de SocketService, deserialization, layer filtering en React

- [DONE] **Shadow Evolution Frontend UI** (SHADOW-EVOLUTION-UI-2026-001)
  - ShadowHub.tsx · CompetitionDashboard.tsx · JustifiedActionsLog.tsx · EdgeConciensiaBadge.tsx
  - ShadowContext.tsx con useShadow() hook · TypeScript 100% · Build SUCCESS (5.40s)

- [DONE] **Shadow WebSocket Backend Integration** (SHADOW-WS-INTEGRATION-2026-001)
  - Router `GET /ws/shadow` con JWT validation + tenant isolation
  - `emit_shadow_status_update()` en MainOrchestrator · 25/25 validate_all PASSED

---

## 📸 Snapshot Sprint 4 (Progreso: 4/5 - Implementación completada, documentación en progreso)

| Métrica | Valor |
|---|---|
| **Arquitectura Base** | v4.1.0-beta.3 (94 tests, 99.8% compliance) |
| **Versión Target** | v4.2.0-beta.1 |
| **Implementación Status** | ✅ 4/4 Componentes Backend COMPLETADOS |
| **Testing** | ✅ 82/82 PASSED (sin regresiones) |
| **Validación Sistema** | ✅ 14/14 módulos PASSED (validate_all.py) |
| **Épica Activa** | E3-E5: Sensorial → Orquestación → Empoderamiento |
| **Última Actualización** | 2 de Marzo, 2026 - 15:30 UTC

---

# SPRINT N1: FOREX CONNECTIVITY STACK — [DONE]

**Inicio**: 14 de Marzo, 2026
**Fin**: 15 de Marzo, 2026
**Objetivo**: Establecer el stack de conectividad FOREX como capa operacional completa. cTrader como conector primario (WebSocket nativo, sin DLL). MT5 estabilizado. ConnectivityOrchestrator 100% data-driven.
**Versión Target**: v4.3.2-beta
**Estado Final**: ✅ COMPLETADO | 6/6 tareas DONE | 25/25 validate_all PASSED
**Trace_ID**: CONN-SSOT-NIVEL1-2026-03-15

---

## 📋 Tareas del Sprint N1

- [DONE] **N1-1: MT5 Single-Thread Executor**
  - ✅ `_MT5Task` dataclass + `_dll_executor_loop` + cola de mensajes implementados
  - ✅ Race condition eliminada entre threads MT5-Background, `_schedule_retry()` y FastAPI caller
  - ✅ MT5 estable como conector alternativo FOREX

- [DONE] **N1-2: cTrader Connector**
  - ✅ `connectors/ctrader_connector.py` creado (~200 líneas, hereda `BaseConnector`)
  - ✅ WebSocket Spotware Open API: tick/OHLC streaming M1 nativo (<100ms latencia)
  - ✅ REST order execution implementado
  - ✅ cTrader posicionado como conector primario FOREX (priority=100)

- [DONE] **N1-3: Data Stack FOREX default**
  - ✅ Prioridades en `DataProviderManager`: cTrader=100, MT5=70, TwelveData/Yahoo=disabled
  - ✅ M1 desactivado por defecto (`enabled: false`) en config
  - ✅ Stocks/futuros deshabilitados hasta Nivel 2

- [DONE] **N1-4: Warning latencia M1**
  - ✅ `ScannerEngine._scan_one()`: detecta provider no-local + M1 activo
  - ✅ WARNING en log + entrada `usr_notifications` con `category: DATA_RISK`

- [DONE] **N1-5: StrategyGatekeeper → MainOrchestrator**
  - ✅ `StrategyGatekeeper` instanciado vía DI en `MainOrchestrator`
  - ✅ Conectado al flujo de señales pre-ejecución (17/17 tests PASSED)

- [DONE] **N1-6: Provisión + Estabilización cTrader** *(15-Mar-2026)*
  - ✅ Bug fix: `client_secret` hardcodeado `""` → `self.config.get("client_secret", "")`
  - ✅ Seed placeholder `ic_markets_ctrader_demo_20001` en `demo_broker_accounts.json`
  - ✅ Script `scripts/utilities/setup_ctrader_demo.py` con guía OAuth2 interactiva
  - ✅ Bug fix MT5 re-activation: `_sync_sys_broker_accounts_to_providers()` preserva `enabled` del usuario
  - ✅ **Refactor arquitectónico**: `_CONNECTOR_REGISTRY` Python eliminado. `load_connectors_from_db()` lee `connector_module`/`connector_class` de `sys_data_providers` vía `importlib`. Zero código por conector.
  - ✅ Schema migration: columnas `connector_module`, `connector_class` en `sys_data_providers` (aditivo)
  - ✅ `save_data_provider()`: `INSERT OR REPLACE` → `INSERT ... ON CONFLICT DO UPDATE SET ... COALESCE(...)` (preserva datos existentes)
  - ✅ `data_providers.json` seed: `connector_module`/`connector_class` en todos los providers

---

## 📸 Snapshot Sprint N1 (Final)

| Métrica | Valor |
|---|---|
| **Versión Sistema** | v4.3.2-beta |
| **Tareas Completadas** | 6/6 ✅ |
| **validate_all.py** | 25/25 PASSED ✅ |
| **Conectores operativos** | cTrader (primary), MT5 (standby), Yahoo (data fallback) |
| **Arquitectura** | DB-driven connector loading — zero hardcoding |
| **Regresiones** | 0 |
| **Fecha Cierre** | 15 de Marzo, 2026 |

---

# SPRINT N2: SEGURIDAD & VISUALIZACIÓN EN VIVO — [TODO]

**Inicio**: 15 de Marzo, 2026
**Objetivo**: Estandarizar la seguridad WebSocket (auth production-ready), desbloquear la visualización en tiempo real en React y activar el filtro de veto por calendario económico.
**Versión Target**: v4.4.0-beta
**Épicas**: E3 (HU 9.3) · E4 (N2-2) · Backlog Suelto (HU 4.7)

---

## 📋 Tareas del Sprint

- [DONE] **N2-2: WebSocket Auth Standardization** *(🔴 SEGURIDAD — 15-Mar-2026)*
  - ✅ `get_ws_user()` creado en `auth.py` — única dependencia WS del sistema (cookie → header → query, sin fallback demo)
  - ✅ `_verify_token()` eliminado de `strategy_ws.py` y `telemetry.py`
  - ✅ Bloque fallback demo eliminado de `telemetry.py` y `shadow_ws.py` (vulnerabilidad crítica cerrada)
  - ✅ 3 routers refactorizados: `strategy_ws.py`, `telemetry.py`, `shadow_ws.py`
  - ✅ 16/16 tests PASSED (`test_ws_auth_standardization.py`)
  - ✅ 25/25 validate_all.py PASSED — sin regresiones
  - Trace_ID: WS-AUTH-STD-N2-2026-03-15

> ⚠️ **DEUDA TÉCNICA DETECTADA — Sprint N2** (no causada por N2-2, detectada durante validación)
> - **Archivo**: `tests/test_shadow_ws_integration.py`
> - **Síntoma**: 9 tests fallan en setup con `AttributeError: module 'core_brain.main_orchestrator' has no attribute 'SocketService'`
> - **Causa raíz**: Los fixtures usan `patch('core_brain.main_orchestrator.SocketService')` pero `main_orchestrator.py` importa `get_socket_service` **localmente** (línea 695), no a nivel de módulo. El target de `patch()` no existe en el namespace del módulo.
> - **Tipo**: Bug de tests (target de patch incorrecto) — sin impacto en producción
> - **Relación con N2-2**: indirecta — `shadow_ws.py` fue refactorizado en esta HU y `test_shadow_ws_integration.py` valida el sistema shadow
> - **Acción pendiente**: Corregir fixtures en `test_shadow_ws_integration.py` — cambiar `patch('core_brain.main_orchestrator.SocketService')` por `patch('core_brain.services.socket_service.get_socket_service')` o inyectar `socket_service` directamente en el constructor de `MainOrchestrator`
> - **Severidad**: Media — no bloquea ejecución pero oculta cobertura real del sistema shadow

- [DONE] **HU 9.3: Frontend WebSocket Rendering** *(15-Mar-2026)*
  - **Root causes corregidos (4)**:
    - RC-A: URL hardcodeada `localhost:8000` en `useSynapseTelemetry`, `AethelgardContext`, `useAnalysisWebSocket` — bypassaba proxy Vite, cookie `a_token` nunca se enviaba.
    - RC-B: `localStorage.getItem('access_token')` en `useStrategyMonitor` — siempre `null` (auth via cookie HttpOnly).
    - RC-C: Prop default `ws://localhost:8000/ws/shadow` en `ShadowHub` — mismo problema cross-origin.
    - RC-D: `useSynapseTelemetry` huérfano — hook completo pero sin consumidor en ningún componente.
  - **Solución**: `ui/src/utils/wsUrl.ts` — función `getWsUrl(path)` usa `window.location.host` para respetar el proxy Vite en dev.
  - **Archivos modificados**: `useStrategyMonitor.ts`, `useSynapseTelemetry.ts`, `AethelgardContext.tsx`, `useAnalysisWebSocket.ts`, `ShadowHub.tsx`, `MonitorPage.tsx`.
  - **Archivos creados**: `ui/src/utils/wsUrl.ts`, `src/__tests__/utils/wsUrl.test.ts`, `src/__tests__/hooks/useStrategyMonitor.test.ts`.
  - **Wiring Glass Box Live**: `MonitorPage` consume `useSynapseTelemetry` mostrando CPU, Memory, Risk Mode, Anomalías en tiempo real vía `/ws/v3/synapse`.
  - ✅ 84/84 vitest PASSED · ✅ 25/25 validate_all.py PASSED

- [TODO] **HU 4.7: Economic Calendar Veto Filter** *(infraestructura lista)*
  - Implementar `get_trading_status()` usando infraestructura `economic_fetch_persist.py` ya existente.
  - Integrar veto en flujo pre-ejecución del `MainOrchestrator`.
  - Prerequisito: ninguno.

