# Dominio 10: INFRA_RESILIENCY (Health, Self-Healing, Anomaly Integration)

## 🎯 Propósito
Garantizar la operatividad perpetua del sistema mediante una infraestructura auto-sanable, monitoreo proactivo de signos vitales y una gestión eficiente de recursos técnicos. Coordinar la respuesta automática a anomalías sistémicas (volatilidad extrema, flash crashes) para transición segura entre estados de salud.

## 🚀 Componentes Críticos
*   **Autonomous Heartbeat**: Sistema de monitoreo de signos vitales que detecta hilos congelados o servicios caídos.
*   **Auto-Healing Engine**: Protocolos de recuperación automática que reinician servicios o resincronizan estados tras detectar fallos.
*   **Resource Sentinel**: Monitor de consumo de CPU, memoria y espacio en disco con alertas de umbral.
*   **Log Management (Linux Style)**: Sistema de rotación diaria con retención estricta de 15 días para optimizar el almacenamiento.
*   **PaperConnector (Hybrid Safety)**: Simulación pura para debugging. **Nota**: Para SHADOW mode (strategy testing), el sistema usa **MT5 DEMO accounts** (real broker, paper account) en lugar de PaperConnector, proporcionando high-fidelity simulation con slippage/spread/commission reales sin riesgo financiero. MT5 DEMO es la opción preferida para calibración de métricas porque proporciona datos auténticos que reflection real market conditions (ver Dominio 05: SHADOW Mode).
*   **Anomaly Health Integration**: Coordinación automática entre detección de eventos extremos (AnomalyService) y transición de estados de salud operacionales.

## ⚕️ Protocolo de Salud (EDGE Autónomo)
El sistema supervisa su propia integridad mediante:
1.  **Auto-Auditoría**: Ejecución programada de validaciones de salud global.
2.  **Propuestas de Gestión**: Detección proactiva de anomalías técnicas reportadas vía `Thoughts` en la UI.
3.  **Veto Técnico**: Capacidad del sistema para detener operaciones si la infraestructura no garantiza fidelidad (ej: alta latencia de red).

## 🔗 Integración Anomalías ↔ Estados de Salud

### Máquina de Estados Operacional
El sistema transita entre 4 estados de salud basándose en dos fuentes de verdad:
- **Anomalías Detectadas** (AnomalyService en Dominio 04)
- **Recursos Disponibles** (Resource Sentinel en Dominio 10)

```
                    ┌─────────────────────────────────────────┐
                    │         NORMAL (Sin Estrés)          │
                    │  • Todas las estrategias activas       │
                    │  • Riesgo: 1% por operación           │
                    └─────────────────────────────────────────┘
                                    ▲
                    Anomalía desaparece + 5 velas estables
                                    │
                  ┌─────────────────────────────────────────┐
                  │   CAUTION (Señal Preventiva)          │
                  │  • 1-2 anomalías en últimas 50 velas   │
                  │  • Riesgo: 0.5% por operación          │
                  │  • UI: Badge amarillo + alerta         │
                  └─────────────────────────────────────────┘
                                    ▲
                    3+ anomalías detectadas O DD > 15%
                                    │
                  ┌─────────────────────────────────────────┐
                  │   DEGRADED (Modo Defensivo)           │
                  │  • Nuevas entradas: BLOQUEADAS         │
                  │  • Cierres: Permitidos                 │
                  │  • Riesgo: 0% (sin riesgo nuevo)       │
                  │  • Lockdown Preventivo: ACTIVO         │
                  │  • UI: Badge rojo + [RISK_PROTOCOL]    │
                  └─────────────────────────────────────────┘
                                    ▲
                    Anomalía crítica (Z > 4) O DD > 20%
                                    │
                  ┌─────────────────────────────────────────┐
                  │   STRESSED (Defensa Total)            │
                  │  • Cancelar órdenes pendientes         │
                  │  • SL → Breakeven (cierre ordenado)   │
                  │  • Broadcast [ANOMALY_DETECTED]       │
                  │  • Intervención manual recomendada    │
                  └─────────────────────────────────────────┘
```

### Detalle de Transiciones

| Evento | De → A | Acciones del Sistema |
|---|---|---|
| Volatilidad Z-Score > 3.0 | NORMAL → CAUTION | Alerta proactiva, reducir tamaño |
| Flash Crash (< -2%) detectado | NORMAL → CAUTION | Broadcast [ANOMALY_DETECTED], incrementar vigilancia |
| 3+ anomalías en 50 velas | CAUTION → DEGRADED | Lockdown activado, cancelar órdenes nuevas, pausa ejecución |
| Anomalía severa (Z > 4.0) | CUALQUIER → STRESSED | [ACCIÓN INMEDIATA] SL→BE, cancel pending, broadcast operador |
| Drawdown > 15% | NORMAL/CAUTION → DEGRADED | Transitar salud, activar defensa |
| Drawdown > 20% (Hard) | CUALQUIER → STRESSED | [STOP TOTAL] Cerrar posiciones, intervención manual |
| Sin anomalías + 5 velas | DEGRADED → CAUTION | Desescalada controlada, reducir volatilidad monitoreo |
| Sin anomalías + 10 velas | CAUTION → NORMAL | Normalización, reactivar estrategias |

### Persistencia y Auditoría de Transiciones
Cada transición de salud se registra en `system_health_history` con:
- `timestamp`: Cuándo ocurrió
- `from_state`: Estado anterior (NORMAL/CAUTION/DEGRADED/STRESSED)
- `to_state`: Estado nuevo
- `trigger`: Causa (ej. "VOLATILITY_ZSCORE_3.2", "CONSECUTIVE_LOSSES_3", "DD_16.5%")
- `anomaly_trace_id`: Referencia a anomaly_events si fue desencadenado por una anomalía
- `duration_seconds`: Cuánto tiempo estuvo en el estado anterior

### Broadcast en Tiempo Real (WebSocket)
Toda transición de salud se comunica a la UI inmediatamente:
```json
{
  "event_type": "HEALTH_STATE_TRANSITION",
  "from_state": "NORMAL",
  "to_state": "CAUTION",
  "trigger": "volatility_zscore_3.2",
  "severity": "HIGH",
  "recommended_action": "Reducir tamaño de posiciones, aumentar vigilancia",
  "timestamp": "2026-03-01T20:45:30Z",
  "trace_id": "BLACK-SWAN-SENTINEL-2026-001"
}
```

## 🖥️ UI/UX REPRESENTATION
*   **Status Vital Badge**: Indicador visual dinámico en el dashboard que resume la salud técnica global (NORMAL=Verde, CAUTION=Amarillo, DEGRADED=Rojo oscuro, STRESSED=Rojo brillante intenso).
*   **System Event Log**: Widget con feed de eventos de infraestructura y anomalías detectadas con timestamps y Trace_IDs.
*   **Resource Gauges**: Medidores dinámicos de carga de sistema, latencia de conexión y volatilidad del mercado.
*   **Health History Timeline**: Vista histórica de transiciones de estado con contexto (duración, trigger, acciones tomadas).

## 📈 Roadmap del Dominio
- [x] Implementación de Path Resilience y validación de integridad ambiental.
- [x] Despliegue del motor de auto-reparación (Repair Protocol).
- [x] **Integración de Anomaly Sentinel con máquina de estados de salud** ✅
  - Estados operacionales (NORMAL/CAUTION/DEGRADED/STRESSED)
  - Transiciones automáticas basadas en Z-Score y Flash Crashes
  - Protocolo Lockdown coordinado
  - Auditoría de transiciones en DB
  - Broadcast en tiempo real a UI
- [x] **Sprint 8: Desbloqueo Operacional del Pipeline** ✅ (24-Mar-2026)
  - HU 10.3: PID Lockfile — singleton guard
  - HU 10.4: Capital dinámico desde `sys_config`
  - HU 10.5: EdgeMonitor connector-agnóstico
- [x] **HU 10.6: AutonomousSystemOrchestrator — Diseño FASE4** ✅ (24-Mar-2026) — 5 sub-componentes documentados, contratos Python, HealingPlaybook, plan incremental 3 fases.
- [x] **Sprint 23: EDGE Reliability — HU 10.10 + HU 10.11** ✅ (27-Mar-2026)
  - HU 10.10: OEM integrado en producción con `shadow_storage` inyectado
  - HU 10.11: 9° check `orchestrator_heartbeat` + `last_results` expuesto vía API
  - Endpoint `GET /api/system/health/edge` + UI `SystemHealthPanel`
- [ ] HU 10.12: Timeout guards en `run_single_cycle()` (Sprint 23 pendiente)
- [ ] HU 10.13: Contract tests para bugs conocidos (Sprint 23 pendiente)
- [ ] Implementación de orquestación de servicios en contenedores aislados.
- [ ] Integración de meta-aprendizaje sobre recursos técnicos.

---

## ⚙️ HU 10.3 — Proceso Singleton: PID Lockfile (24-Mar-2026)

**Trace_ID**: `PIPELINE-UNBLOCK-SINGLETON-2026-03-24`

### Problema detectado
`start.py` no verificaba si ya había una instancia activa. Se detectaron 2×`start.py` + 2×uvicorn corriendo simultáneamente (PIDs 31680 y 32856), causando ciclos duplicados, doble escritura en DB y métricas distorsionadas.

### Solución implementada (`start.py`)

```python
_LOCK_PATH = Path("data_vault/aethelgard.lock")

def _acquire_singleton_lock(lock_path: Path = _LOCK_PATH) -> bool:
    """Crea lockfile con PID. Retorna False si otra instancia está activa."""
    if lock_path.exists():
        pid = int(lock_path.read_text().strip())
        if psutil.pid_exists(pid) and pid != os.getpid():
            return False  # otra instancia viva → abortar
    lock_path.write_text(str(os.getpid()))
    return True

def _release_singleton_lock(lock_path: Path = _LOCK_PATH) -> None:
    lock_path.unlink(missing_ok=True)
```

Integrado en `main()`: abort antes de inicializar cualquier componente. Limpieza en bloque `finally`. **Tests**: 9/9 PASSED.

---

## ⚙️ HU 10.4 — Capital Dinámico desde `sys_config` (24-Mar-2026)

**Trace_ID**: `PIPELINE-UNBLOCK-CAPITAL-DB-2026-03-24`

### Problema detectado
`RiskManager` recibía `initial_capital=10000.0` hardcodeado en `start.py`. La DB tenía `account_balance: 8386.09` en `sys_config` — el sistema calculaba riesgo sobre un capital ficticio.

### Solución implementada (`start.py`)

```python
def _read_initial_capital(storage) -> float:
    """Lee account_balance desde sys_config. Fallback: 10000.0 con WARNING."""
    cfg = storage.get_sys_config()
    balance = cfg.get("account_balance", 0)
    if balance and float(balance) > 0:
        return float(balance)
    return 10000.0  # fallback con WARNING en log
```

```python
initial_capital = _read_initial_capital(storage)
risk_manager = RiskManager(storage=storage, initial_capital=initial_capital, ...)
```

**Tests**: incluidos en `tests/test_start_singleton.py` — 9/9 PASSED.

---

## ⚙️ HU 10.5 — EdgeMonitor Connector-Agnóstico (24-Mar-2026)

**Trace_ID**: `PIPELINE-UNBLOCK-EDGE-AGNOSTIC-2026-03-24`

### Problema detectado
`EdgeMonitor.__init__` aceptaba `mt5_connector: Optional[Any]` hardcodeado. El sistema tiene múltiples conectores (MT5, cTrader, Paper) y la validación puntual a MT5 es una violación del principio de agnosticismo de infraestructura. Además emitía `INFO/DEBUG` silencioso cuando MT5 no estaba inyectado — ruido operacional innecesario.

### Solución implementada (`core_brain/edge_monitor.py`)

**Antes**: `mt5_connector: Optional[Any] = None`
**Después**: `connectors: Dict[str, Any]` — igual que `OrderExecutor`

```python
def __init__(self, ..., connectors: Optional[Dict[str, Any]] = None,
             mt5_connector: Optional[Any] = None):
    # Compatibilidad hacia atrás: mt5_connector= se envuelve automáticamente
    if connectors is not None:
        self.connectors = connectors
    elif mt5_connector is not None:
        self.connectors = {"mt5": mt5_connector}  # backward compat
    else:
        self.connectors = {}
```

Nuevo método público:
```python
def _get_active_connectors(self) -> Dict[str, Any]:
    """Retorna todos los conectores disponibles — agnóstico de tipo."""
    return self.connectors
```

`_get_mt5_connector()` conservado como wrapper de backward compat.

**Wiring en `start.py`**:
```python
edge_monitor = EdgeMonitor(
    storage=storage,
    connectors=active_connectors,  # Dict genérico, no MT5-específico
    trade_listener=trade_closure_listener
)
```

**Tests**: `TestEdgeMonitorConnectorAgnostic` (6 tests) + `TestEdgeMonitorMt5Warning` (4 tests) — 10/10 PASSED.

---

## 🧠 HU 10.6 — AutonomousSystemOrchestrator: Diseño FASE4 (PENDIENTE)

**Trace_ID**: `FASE4-AUTONOMOUS-ORCHESTRATOR-DESIGN-2026-03-24`
**Estado**: Diseño documentado, implementación en backlog.

### Contexto
El sistema cuenta con **13 componentes EDGE** operativos que actúan de forma descoordinada:

| Componente | Ubicación | Función |
|---|---|---|
| `OperationalEdgeMonitor` | `core_brain/operational_edge_monitor.py` | 9 invariantes de negocio (incluye heartbeat del loop) |
| `EdgeTuner` | `core_brain/edge_tuner.py` | Calibración automática de parámetros |
| `DedupLearner` | `core_brain/signal_deduplicator.py` | Aprendizaje de ventanas de dedup |
| `CoherenceMonitor` | `core_brain/coherence_monitor.py` | Detección de drift SHADOW vs LIVE |
| `DrawdownMonitor` | `core_brain/drawdown_monitor.py` | Umbrales Soft/Hard de drawdown |
| `ExecutionFeedbackCollector` | `core_brain/execution_feedback.py` | Tracking de fallos de ejecución |
| `CircuitBreaker` | `core_brain/circuit_breaker.py` | Degradación LIVE → QUARANTINE |
| `PositionSizeMonitor` | `core_brain/position_size_monitor.py` | Validación de tamaños de posición |
| `RegimeClassifier` | `core_brain/regime.py` | Clasificación de régimen de mercado |
| `ClosingMonitor` | `core_brain/monitor.py` | Cierre automático de posiciones |
| `AutonomousHealthService` | `core_brain/health_service.py` | Heartbeat y auto-recuperación |
| `HealthManager` | `core_brain/health_manager.py` | Gestión de estados de salud |
| `CoherenceService` | `core_brain/services/coherence_service.py` | Coherencia entre módulos |

### Arquitectura propuesta: `AutonomousSystemOrchestrator`

```
AutonomousSystemOrchestrator
├── DiagnosticsEngine        → Correlaciona síntomas con causas raíz (grafo de dependencias)
├── BaselineTracker          → Aprende qué es "normal" por hora del día / sesión de mercado
├── HealingPlaybook          → Catálogo de acciones correctivas seguras por tipo de problema
├── ObservabilityLedger      → Tabla sys_agent_events: traza cada decisión autónoma
└── EscalationRouter         → Notificación con diagnóstico completo cuando el healing falla
```

**Niveles de autonomía configurables** (desde `sys_config`):
- `OBSERVE`: Solo diagnóstico y log — sin acciones
- `SUGGEST`: Diagnóstico + recomendaciones en UI — sin ejecución
- `HEAL`: Diagnóstico + ejecución de acciones dentro del HealingPlaybook

### DDL propuesto para `sys_agent_events`
```sql
CREATE TABLE IF NOT EXISTS sys_agent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,        -- DIAGNOSIS | HEALING_ATTEMPT | ESCALATION
    component TEXT NOT NULL,         -- componente EDGE afectado
    symptom TEXT NOT NULL,           -- descripción del síntoma detectado
    root_cause TEXT,                 -- causa raíz inferida por DiagnosticsEngine
    action_taken TEXT,               -- acción ejecutada (NULL si OBSERVE mode)
    result TEXT,                     -- SUCCESS | FAILED | SKIPPED
    autonomy_level TEXT NOT NULL,    -- OBSERVE | SUGGEST | HEAL
    trace_id TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### Detalle de Sub-componentes

#### 1. DiagnosticsEngine

Correlaciona síntomas observables con causas raíz mediante un **grafo de dependencias estático** declarado en código. El grafo modela las relaciones causales entre los 13 componentes EDGE.

**Grafo de dependencias (dirección: afecta → afectado)**:
```
OperationalModeManager ──→ BacktestOrchestrator
                       ──→ MainOrchestrator (frecuencias)

RegimeClassifier ──→ ScenarioBacktester (_split_into_cluster_slices)
                ──→ CoherenceMonitor (drift SHADOW vs LIVE)
                ──→ HealthManager (umbral de anomalías)

EdgeMonitor ──→ HealthManager (transiciones NORMAL/CAUTION/DEGRADED/STRESSED)
            ──→ CircuitBreaker (degradación LIVE → QUARANTINE)

OperationalEdgeMonitor ──→ DrawdownMonitor (umbrales Soft/Hard)
                       ──→ PositionSizeMonitor (validación de capital)
                       ──→ BacktestOrchestrator (presupuesto)

ExecutionFeedbackCollector ──→ EdgeTuner (calibración de parámetros)
                           ──→ CircuitBreaker (fallos acumulados)

DedupLearner ──→ SignalSelector (ventana de dedup)
             ──→ CooldownManager (cooldown por señal)
```

**Algoritmo de diagnóstico**:
1. Recibe un `symptom` con `component` afectado.
2. Navega el grafo hacia arriba (causas) y hacia abajo (efectos secundarios).
3. Consulta `sys_agent_events` para detectar síntomas recurrentes en las últimas N horas.
4. Emite un `root_cause` con nivel de confianza (`HIGH` / `MEDIUM` / `LOW`).

**Reglas de correlación pre-definidas**:

| Síntoma | Causa raíz inferida | Confianza |
|---|---|---|
| `BacktestOrchestrator: 0 slices evaluados` | `RegimeClassifier: ADX siempre 0` | HIGH |
| `CircuitBreaker: LIVE → QUARANTINE` | `ExecutionFeedbackCollector: >3 fallos/hora` | HIGH |
| `CoherenceMonitor: drift > umbral` | `RegimeClassifier: cambio de régimen no propagado` | MEDIUM |
| `SignalSelector: 0 señales seleccionadas` | `DedupLearner: ventana demasiado amplia` o `CooldownManager: cooldown excesivo` | MEDIUM |
| `HealthManager: NORMAL → CAUTION repetitivo` | `BaselineTracker: umbral Z-Score mal calibrado para esta sesión` | LOW |

---

#### 2. BaselineTracker

Aprende qué es "normal" para cada componente segmentando por **sesión de mercado** (Tokyo / London / New York / Off-hours) y **hora local del servidor**.

**Métricas rastreadas por componente**:

| Componente | Métrica baseline |
|---|---|
| `BacktestOrchestrator` | Slices evaluados/hora, budget medio |
| `SignalSelector` | Señales seleccionadas/hora |
| `EdgeMonitor` | Latencia media de checks |
| `OperationalEdgeMonitor` | Nº invariantes en WARNING/hora |
| `HealthManager` | Frecuencia de transiciones de estado |

**Persistencia**: tabla `sys_baseline_stats` (lógica compartida con `sys_audit_logs`). No requiere DDL nuevo en el Sprint — puede usar `sys_audit_logs` con `user_id='BASELINE_TRACKER'` hasta que se justifique una tabla dedicada.

**Ventana de aprendizaje**: 7 días de historia. El baseline se recalcula cada 24h durante off-hours.

---

#### 3. HealingPlaybook

Catálogo de acciones correctivas seguras, indexado por `(component, root_cause)`. Cada entrada define la acción, su nivel mínimo de autonomía requerido y si es reversible.

| Problema | Componente | Acción | Autonomía mín. | Reversible |
|---|---|---|---|---|
| ADX siempre 0 | `RegimeClassifier` | Llamar `classifier.load_ohlc(df)` con últimos 200 bars desde DB | `HEAL` | Sí |
| Budget `DEFERRED` persistente | `OperationalModeManager` | Log + esperar 5 min → re-evaluar psutil | `OBSERVE` | N/A |
| CircuitBreaker en QUARANTINE | `CircuitBreaker` | Notificar operador con diagnóstico completo | `SUGGEST` | No (manual) |
| DedupLearner: ventana > 120 min | `DedupLearner` | Resetear `learned_window` a 30 min (default seguro) | `HEAL` | Sí |
| CooldownManager: cooldown > 4h | `CooldownManager` | Reducir a 60 min para el instrumento afectado, log | `HEAL` | Sí |
| HealthManager: CAUTION en off-hours | `HealthManager` | Ajustar umbral Z-Score +0.5 para sesión off-hours | `SUGGEST` | Sí |
| `sys_agent_events` > 50k filas | `ObservabilityLedger` | Purgar eventos > 30 días | `HEAL` | No (datos históricos) |

**Acciones explícitamente prohibidas en el Playbook** (fuera del alcance de autonomía):
- Modificar `sys_strategies.mode` (BACKTEST/SHADOW/LIVE) — requiere intervención humana
- Cancelar trades activos — dominio exclusivo del `ClosingMonitor` bajo órdenes del `HealthManager`
- Modificar thresholds de riesgo en `sys_config` — requiere confirmación del operador

---

#### 4. ObservabilityLedger

Wrapper sobre `sys_agent_events` que garantiza trazabilidad completa de cada decisión autónoma. Cada escritura incluye un `trace_id` enlazado al evento disparador.

**Formato de entrada estándar**:
```python
ledger.record(
    event_type="HEALING_ATTEMPT",
    component="DedupLearner",
    symptom="learned_window=180min (> 120min umbral)",
    root_cause="Aprendizaje en sesión de baja liquididad — ventana sesgada",
    action_taken="Reset learned_window → 30min",
    result="SUCCESS",
    autonomy_level="HEAL",
    trace_id="ASO-HEAL-20260324-001"
)
```

**Política de retención**: 30 días. Purga automática por el Playbook (entrada: `sys_agent_events > 50k filas`).

---

#### 5. EscalationRouter

Se activa cuando el `HealingPlaybook` no tiene acción para un problema, o cuando una acción `HEAL` falla. Emite una notificación estructurada con el diagnóstico completo del `DiagnosticsEngine`.

**Canales de escalación** (configurables en `sys_config`):
- `WEBSOCKET`: broadcast a la UI — disponible hoy (usa infraestructura de `broadcast_shadow_update`)
- `LOG_CRITICAL`: always-on fallback

**Payload de escalación**:
```json
{
  "event_type": "ESCALATION",
  "component": "CircuitBreaker",
  "symptom": "LIVE → QUARANTINE (3er disparo en 2h)",
  "root_cause": "ExecutionFeedbackCollector: 7 fallos ORDER_REJECTED en 60min",
  "dependency_chain": ["ExecutionFeedbackCollector", "CircuitBreaker", "HealthManager"],
  "healing_attempted": "N/A — acción prohibida en Playbook",
  "recommended_action": "Revisar conectividad con broker y validar account_balance",
  "autonomy_level": "SUGGEST",
  "trace_id": "ASO-ESC-20260324-001",
  "timestamp": "2026-03-24T14:32:00Z"
}
```

---

### Flujos de Secuencia por Nivel de Autonomía

#### OBSERVE — Solo diagnóstico y log
```
Síntoma detectado
      │
      ▼
DiagnosticsEngine.correlate(symptom, component)
      │
      ▼
ObservabilityLedger.record(event_type="DIAGNOSIS", action_taken=None)
      │
      ▼
[FIN — sin acciones externas]
```

#### SUGGEST — Diagnóstico + recomendación en UI
```
Síntoma detectado
      │
      ▼
DiagnosticsEngine.correlate(symptom, component)
      │
      ▼
HealingPlaybook.lookup(component, root_cause)
      │
      ├─ acción encontrada ──→ EscalationRouter.suggest(action, diagnosis)
      │                              │
      │                              ▼
      │                        WebSocket broadcast "SUGGESTION"
      │
      └─ sin acción ──────────→ EscalationRouter.escalate(diagnosis)
      │
      ▼
ObservabilityLedger.record(event_type="DIAGNOSIS", result="SUGGESTED")
```

#### HEAL — Diagnóstico + ejecución automática
```
Síntoma detectado
      │
      ▼
DiagnosticsEngine.correlate(symptom, component)
      │
      ▼
HealingPlaybook.lookup(component, root_cause)
      │
      ├─ acción encontrada + permitida ──→ HealingPlaybook.execute(action)
      │                                           │
      │                               ┌───────────┴───────────┐
      │                           SUCCESS                   FAILED
      │                               │                       │
      │                        Ledger.record              EscalationRouter.escalate
      │                        result="SUCCESS"           result="FAILED"
      │
      └─ sin acción / prohibida ──────→ EscalationRouter.escalate(diagnosis)
```

---

### Contrato de Interfaces Python

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AutonomyLevel(str, Enum):
    OBSERVE  = "OBSERVE"
    SUGGEST  = "SUGGEST"
    HEAL     = "HEAL"


@dataclass
class Diagnosis:
    component: str
    symptom: str
    root_cause: Optional[str]
    confidence: str          # HIGH | MEDIUM | LOW
    dependency_chain: list[str]
    trace_id: str


@dataclass
class HealingAction:
    description: str
    min_autonomy: AutonomyLevel
    reversible: bool
    # callable que ejecuta la acción; None si solo notificación
    executor: Optional[callable] = None


class DiagnosticsEngine:
    def correlate(self, symptom: str, component: str) -> Diagnosis: ...


class BaselineTracker:
    def is_abnormal(self, component: str, metric: str, value: float) -> bool: ...
    def update(self, component: str, metric: str, value: float) -> None: ...


class HealingPlaybook:
    def lookup(self, component: str, root_cause: str) -> Optional[HealingAction]: ...
    def execute(self, action: HealingAction) -> str: ...   # SUCCESS | FAILED | SKIPPED


class ObservabilityLedger:
    def record(self, event_type: str, component: str, symptom: str,
               root_cause: Optional[str], action_taken: Optional[str],
               result: Optional[str], autonomy_level: str, trace_id: str) -> None: ...


class EscalationRouter:
    def suggest(self, action: HealingAction, diagnosis: Diagnosis) -> None: ...
    def escalate(self, diagnosis: Diagnosis, healing_failed: bool = False) -> None: ...


class AutonomousSystemOrchestrator:
    """
    Punto de entrada único. Recibe síntomas de los 13 componentes EDGE
    y coordina el pipeline Diagnóstico → Playbook → Healing → Escalación.

    Wiring en MainOrchestrator:
        aso = AutonomousSystemOrchestrator(
            storage=storage,
            autonomy_level=AutonomyLevel(sys_config.get("aso_autonomy_level", "OBSERVE")),
            ws_broadcast=broadcast_shadow_update,
        )
        # Llamado desde cada componente EDGE al detectar anomalía:
        await aso.handle_symptom(symptom="...", component="RegimeClassifier")
    """
    def __init__(
        self,
        storage: "StorageManager",
        autonomy_level: AutonomyLevel,
        ws_broadcast: Optional[callable] = None,
    ) -> None: ...

    async def handle_symptom(self, symptom: str, component: str) -> None: ...
```

---

### Plan de Implementación Incremental (3 fases)

| Fase | Alcance | Sprint sugerido | Prerequisito |
|---|---|---|---|
| **FASE 4A** | `ObservabilityLedger` + DDL `sys_agent_events` + wiring básico en `MainOrchestrator` (OBSERVE hardcodeado) | Sprint 11 | E10 Sprint MV completo |
| **FASE 4B** | `DiagnosticsEngine` con grafo estático + `BaselineTracker` (7 días) + `EscalationRouter` WebSocket | Sprint 12 | FASE 4A |
| **FASE 4C** | `HealingPlaybook` completo + nivel `HEAL` con acciones ejecutables + tests de integración end-to-end | Sprint 13 | FASE 4B |

**Criterio de entrada a FASE 4A**: al menos 2 estrategias promovidas a SHADOW con datos reales del broker (scores > 0.75). Sin ese baseline, el `BaselineTracker` no tiene datos suficientes para aprender "normal".

---

### Integración con Componentes Existentes

```
MainOrchestrator
    │
    ├── OperationalModeManager ──────────────────────────────┐
    │       │                                                │
    │       └── detecta contexto → AutonomousSystemOrchestrator
    │                                       │
    │   ┌───────────────────────────────────┤
    │   │  Componentes EDGE emiten síntomas │
    │   │  via aso.handle_symptom(...)      │
    │   │                                   │
    │   ├── OperationalEdgeMonitor ─────────┤
    │   ├── EdgeMonitor ────────────────────┤
    │   ├── CircuitBreaker ─────────────────┤
    │   ├── DedupLearner ──────────────────┤
    │   ├── HealthManager ─────────────────┤
    │   └── BacktestOrchestrator ──────────┘
    │
    └── [ASO resuelve internamente: Diagnostics → Playbook → Ledger → Escalation]
```

**Nota de implementación**: el `AutonomousSystemOrchestrator` es **observador pasivo** hasta FASE 4C. Los componentes EDGE mantienen su lógica propia; el ASO solo recibe notificaciones vía callbacks, sin acoplar su lógica interna.

---

## ⚙️ HU 10.10 — OEM Production Integration (27-Mar-2026)

**Trace_ID**: `EDGE-RELIABILITY-OEM-INTEGRATION-2026`
**Épica**: E13 | **Sprint**: 23

### Problema
El `OperationalEdgeMonitor` existía con 8 checks implementados y 27 tests pasando, pero **nunca fue instanciado en `start.py`**. Sus invariantes de negocio nunca se ejecutaban en producción. Adicionalmente, el check `shadow_sync` retornaba siempre `WARN: shadow_storage no inyectado` porque el constructor no recibía el parámetro.

### Solución implementada

**`start.py`** — bloque `8.6` (después del SHADOW pool, antes de `AutonomousHealthService`):
```python
from core_brain.operational_edge_monitor import OperationalEdgeMonitor
from data_vault.shadow_db import ShadowStorageManager

_conn = getattr(storage, 'conn', None) or getattr(storage, 'connection', None)
_shadow_storage_for_oem = ShadowStorageManager(_conn) if _conn else None

oem = OperationalEdgeMonitor(
    storage=storage,
    shadow_storage=_shadow_storage_for_oem,
    interval_seconds=300,
)
oem.start()

from core_brain.server import set_oem_instance
set_oem_instance(oem)
```

**`core_brain/server.py`** — singleton accesible por la API:
```python
_oem_instance = None

def set_oem_instance(oem) -> None: ...
def get_oem_instance():            ...
```

**`core_brain/api/routers/system.py`** — endpoint REST:
```
GET /api/system/health/edge
→ { status, checks: {name: {status, detail}}, failing, warnings, last_checked_at }
```

**UI**: `ui/src/hooks/useOemHealth.ts` (polling HTTP 15 s) + `ui/src/components/diagnostic/SystemHealthPanel.tsx` (grid de 9 cards integrado en `MonitorPage`).

### Artefactos
- `start.py` (bloque 8.6)
- `core_brain/server.py` (`set_oem_instance`, `get_oem_instance`)
- `core_brain/api/routers/system.py` (`GET /api/system/health/edge`)
- `ui/src/hooks/useOemHealth.ts`
- `ui/src/components/diagnostic/SystemHealthPanel.tsx`
- `ui/src/components/diagnostic/MonitorPage.tsx` (integración)
- `tests/test_oem_production_integration.py` (9 tests)

---

## ⚙️ HU 10.11 — OEM Loop Heartbeat Check (27-Mar-2026)

**Trace_ID**: `EDGE-RELIABILITY-OEM-HEARTBEAT-2026`
**Épica**: E13 | **Sprint**: 23

### Problema
El loop principal (`run_single_cycle()`) podía bloquearse indefinidamente por un `await` sin timeout (ej. `fetch_ohlc()` con red caída). El OEM no tenía ningún check que detectara este estado — el sistema simplemente dejaba de avanzar sin generar ninguna alerta.

### Solución implementada

**`core_brain/operational_edge_monitor.py`**:

Nuevo 9° check `_check_orchestrator_heartbeat()`:
```python
MAX_HEARTBEAT_GAP_WARN_MINUTES = 10
MAX_HEARTBEAT_GAP_FAIL_MINUTES = 20

def _check_orchestrator_heartbeat(self) -> CheckResult:
    heartbeats = self.storage.get_module_heartbeats()
    orchestrator_ts = heartbeats.get("orchestrator")
    # Sin heartbeat → WARN (primer arranque)
    # gap < 10 min → OK
    # gap 10-20 min → WARN
    # gap > 20 min → FAIL (posible bloqueo del loop)
```

**Regla CRITICAL actualizada**: el estado global es `CRITICAL` si `orchestrator_heartbeat` falla (solo), o si >= 2 checks fallan. Antes: >= 3 checks.

**`last_results` y `last_checked_at`** añadidos como atributos de instancia actualizados en cada ciclo del thread — consumidos por el endpoint REST.

### Diagrama de estados del check

```
heartbeat inexistente → WARN  (sistema puede estar arrancando)
gap < 10 min          → OK    (loop activo y saludable)
gap 10–20 min         → WARN  (loop lento — posible carga alta)
gap > 20 min          → FAIL  (CRITICAL — loop posiblemente bloqueado)
```

### Artefactos
- `core_brain/operational_edge_monitor.py` (check, constantes, last_results, CRITICAL rule)
- `tests/test_oem_heartbeat_check.py` (10 tests: OK/WARN/FAIL, umbrales exactos, integración health_summary)

