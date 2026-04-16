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

## I.B Contrato de Confianza Operativa (Evidencia Obligatoria)

**Vigente desde:** 2026-04-13 | Trace_ID: E19-RUNTIME-CONTRACT-HARDENING-2026-04-13

### Regla de Oro

La confianza del sistema se declara solo con evidencia reproducible. Ningún cambio runtime se considera cerrado por narrativa o resultado aislado.

### Fuente Canónica de Confianza

- La matriz oficial reside en `governance/AUDITORIA_ESTADO_REAL.md`.
- Debe actualizarse en cada HU que toque estrategias, pipeline de señales, riesgo o salud operacional.

### Estructura mínima de la matriz

| Campo | Requisito |
|---|---|
| Componente | Nombre técnico del módulo auditado |
| Esperado | Comportamiento contractual |
| Observado | Comportamiento runtime real |
| Estado | OK / PARCIAL / CRÍTICO |
| Evidencia | logs, DB, tests con referencia concreta |
| Acción | corrección o seguimiento obligatorio |

### Criterio de Cierre de HU

Una HU runtime no puede declararse `[DONE]` sin:
1. `validate_all.py` en verde.
2. Matriz de confianza actualizada.
3. Ventana de monitoreo con evidencia de operación real.

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

---

## IV. EDGE Resilience Architecture (ETI-2 — 2026-04-16)

**Trace_ID**: EDGE_Resilience_Improvements-2026-04-16

### Principio

El sistema debe autoajustarse y degradar de forma controlada ante locks SQLite persistentes, sin intervención manual del operador.

### Componentes

| Componente | Responsabilidad |
|---|---|
| `data_vault/db_policy_tuner.py` | Auto-tuning de `busy_timeout`; fallback read-only; tracking de lock events |
| `data_vault/database_manager.py` | Integra `DBPolicyTuner`; activa read-only en degradación; registra lock events |
| `utils/alerting.py` | Despacho multi-canal (LOG_ONLY · EMAIL · TELEGRAM) con rate-limiting 5 min |
| `core_brain/operational_edge_monitor.py` | Check `db_lock_rate_anomaly`; alerta proactiva via `AlertingService` |

### Contrato de Auto-Tuning

```
p95_ms ≥ P95_CRITICAL_MS (2000ms)  → busy_timeout += 2 × STEP (30s)
p95_ms ≥ P95_WARN_MS (500ms)       → busy_timeout += 1 × STEP (15s)
lock_rate ≥ 15 eventos/min          → igual que P95_CRITICAL
lock_rate ≥ 5 eventos/min           → igual que P95_WARN
p95_ms < 250ms y lock_rate < 2.5/m → busy_timeout -= STEP (recovery)

Límites: [30s, 300s]   Throttle: 1 evaluación cada 30s por db_path
```

### Contrato de Fallback Read-Only

Cuando `recover_from_lock()` retorna `should_degrade=True`:
1. `DatabaseManager` marca la BD como degradada (`_degraded_dbs`).
2. `DBPolicyTuner.apply_read_only_mode()` aplica `PRAGMA query_only=1`.
3. Todo intento de `transaction()` lanza `OperationalError("SOLO-LECTURA")`.
4. Las lecturas via `execute_query()` continúan operando normalmente.
5. **Restauración manual**: `clear_degraded(db_path)` revierte ambos estados.

### Contrato de Alertas

- Canal por defecto: `LOG_ONLY` (sin config).
- Config vía variables de entorno (`ALERT_CHANNELS`, `ALERT_SMTP_*`, `ALERT_TELEGRAM_*`).
- Rate-limiting: máximo 1 alerta por `(canal, key)` cada 300 segundos.
- Severity CRITICAL: ≥ 2 checks OEM fallando, o `orchestrator_heartbeat` / `db_lock_rate_anomaly`.

### Reglas Operativas

- `DBPolicyTuner` es instanciado exclusivamente por `DatabaseManager` — nunca instanciar directamente.
- `AlertingService` debe inyectarse en `OperationalEdgeMonitor`; si se omite, usa `LOG_ONLY`.
- Los umbrales (`P95_WARN_MS`, `LOCK_RATE_WARN_PER_MIN`, etc.) son constantes en `db_policy_tuner.py` — no duplicar en otro módulo.

---

## IV. Contrato de Respuesta EDGE ante Volatilidad Extrema

**Vigente desde:** 2026-04-16 | ETI_ID: EDGE_Volatility_Response_2026-04-16

### Problema

El `AnomalySentinel` detectaba eventos de volatilidad extrema (Z-Score fuera de rango, spread anómalo) pero solo los logueaba como WARNING, sin respuesta operativa automática.

### Solución Implementada

Patrón Observer entre `AnomalySentinel` (emisor) y `VolatilityResponseManager` (suscriptor), orquestado opcionalmente por `OperationalEdgeMonitor`.

### Componentes

| Componente | Archivo | Rol |
|---|---|---|
| `VolatilityEvent` | `core_brain/services/anomaly_sentinel.py` | Dataclass del evento (trace_id, protocol, z_score, spread_ratio, timestamp) |
| `AnomalySentinel.register_listener()` | `core_brain/services/anomaly_sentinel.py` | Registra callbacks; emite tras cada `get_defense_protocol()` no-NONE |
| `VolatilityResponseManager` | `core_brain/services/edge_volatility_responder.py` | Mantiene estado, aplica acciones, auto-revierte |
| `OperationalEdgeMonitor._init_vrm()` | `core_brain/operational_edge_monitor.py` | Wire-up: crea VRM y lo suscribe al sentinel inyectado |

### Estados del VRM

| Estado | Trigger | Acciones |
|---|---|---|
| `NORMAL` | Inicio o auto-reversión | Factor de riesgo = 1.0 |
| `ELEVATED` | `DefenseProtocol.WARNING` | Alerta WARNING, log, auditoría |
| `LOCKDOWN` | `DefenseProtocol.LOCKDOWN` | Alerta CRITICAL, factor de riesgo = 0.5 (configurable), auditoría |

### Auto-Reversión

El `OperationalEdgeMonitor` llama `vrm.check_auto_reversal(sentinel)` en cada ciclo de monitoreo. Tras `auto_revert_consecutive` (default: 3) lecturas consecutivas con `DefenseProtocol.NONE`, el VRM revierte a `NORMAL` y restaura el factor de riesgo a 1.0.

### Trazabilidad

Cada acción persiste en `sys_config` (`edge_volatility_state`, `edge_volatility_last_trace_id`, `edge_volatility_risk_factor`) y en `sys_audit_logs` con el mismo `Trace_ID` del evento detectado por el sentinel.

### Reglas Operativas

- `VolatilityResponseManager` se inyecta en `OperationalEdgeMonitor` vía parámetro `sentinel`; sin sentinel, el VRM no se crea (comportamiento legacy preservado).
- No instanciar `VolatilityResponseManager` directamente desde el orquestador — siempre vía `OperationalEdgeMonitor`.

---

## VII. Respuesta EDGE a Stale Connection

**ETI_ID**: `EDGE_StaleConnection_Response_2026-04-16`
**Trace_ID**: `EDGE_StaleConnection_Response_2026-04-16`
**Archivos**: `data_vault/database_manager.py`, `core_brain/operational_edge_monitor.py`, `tests/test_edge_stale_connection.py`

### Problema

`DatabaseManager` detecta y recrea conexiones "stale" silenciosamente. Sin monitoreo de frecuencia, una degradación sostenida de infraestructura podía pasar desapercibida.

### Solución

**DatabaseManager** emite un evento por cada reconexión stale:

- Nuevo método `register_stale_hook(callback)` — registra listeners `(db_path, trace_id) -> None`.
- `_emit_stale_event(db_path, trace_id)` — despacha a todos los hooks; excepciones en callbacks son contenidas.
- Cada evento incluye un `trace_id` prefijado `STALE-` para trazabilidad.

**OperationalEdgeMonitor** se suscribe automáticamente al inicializar:

- `_register_stale_hook()` — registra `_on_stale_connection` en el DatabaseManager inyectado (o singleton).
- `_on_stale_connection(db_path, trace_id)` — registra el evento en un `deque` deslizante de 500 entradas.
- Evalúa la tasa en la ventana activa (`STALE_CONN_WINDOW_SECONDS = 60`):
  - `≥ STALE_CONN_WARN_PER_MIN (3/min)` → alerta `WARNING`.
  - `≥ STALE_CONN_FAIL_PER_MIN (8/min)` → alerta `CRITICAL`.
  - `≥ STALE_CONN_DEGRADE_THRESHOLD (20 eventos)` → activa modo solo-lectura vía `DBPolicyTuner`.
- Nuevo check `stale_connection_anomaly` en `run_checks()`.
- `get_stale_event_summary()` — observable para API y diagnóstico.
- `clear_stale_degraded(db_path)` — revierte degradación y limpia historial. **Acción reversible.**

### Umbrales (configurables como constantes de clase)

| Constante | Default | Significado |
|---|---|---|
| `STALE_CONN_WARN_PER_MIN` | 3.0 | Tasa que activa alerta WARNING |
| `STALE_CONN_FAIL_PER_MIN` | 8.0 | Tasa que activa alerta CRITICAL |
| `STALE_CONN_WINDOW_SECONDS` | 60 | Ventana de medición |
| `STALE_CONN_DEGRADE_THRESHOLD` | 20 | Eventos en ventana → modo solo-lectura |

### Trazabilidad

Cada evento stale tiene `trace_id = STALE-XXXXXXXX`. Las alertas y degradaciones se registran en `AlertingService` con `key=stale_conn_warn:{db_path}` / `stale_conn_critical:{db_path}` / `stale_conn_degraded:{db_path}`.

### Tests

`tests/test_edge_stale_connection.py` — 24 tests, 5 clases:
- `TestDatabaseManagerStaleHook` — registro, emisión, aislamiento de excepciones, integración real.
- `TestOemOnStaleConnection` — registro de evento, alertas por umbral, degradación.
- `TestOemCheckStaleConnectionAnomaly` — lógica del check OEM.
- `TestOemClearStaleDegraded` — reversión completa y limpieza de historial.
- `TestOemStaleEventSummary` — resumen observable.
- El factor de riesgo reducido (`edge_volatility_risk_factor`) debe ser leído por el ejecutor antes de calcular el tamaño de posición.
