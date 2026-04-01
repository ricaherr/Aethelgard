# Dominio 10: INFRA_RESILIENCY (Health, Self-Healing, Anomaly Integration)

## 🎯 Propósito
Garantizar la operatividad perpetua del sistema mediante una infraestructura auto-sanable de **resiliencia granular**, monitoreo proactivo de signos vitales y gestión eficiente de recursos técnicos. Implementa la **Degradación Elegante**, permitiendo aislar fallos a nivel de activo, estrategia o servicio sin detener el motor principal de Alpha Generation, coordinado por un `ResilienceManager` central.

## 🚀 Componentes Críticos
*   **Autonomous Heartbeat**: Sistema de monitoreo de signos vitales que detecta hilos congelados o servicios caídos.
*   **ResilienceManager (El Cerebro Inmunológico)**: Evalúa la acumulación de eventos granulares y transita la postura global del orquestador.
*   **ResilienceInterface**: Contrato estándar obligatorio para componentes de diagnóstico.
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

### Arquitectura de Resiliencia Granular (Capas EDGE L0 - L3)
El sistema implementa 4 capas de contención. La escalada al nivel superior está prohibida si el fallo puede ser contenido y sanado en el nivel inferior.

| Capa | Nivel | Entidad Afectada | Acción Típica | Ejemplo de Disparador |
|:---|:---|:---|:---|:---|
| **L0** | `ASSET` | Instrumento (ej. `XAUUSD`) | `MUTE` | Spread > 300% del promedio o liquidez insuficiente. |
| **L1** | `STRATEGY` | Instancia Algorítmica | `QUARANTINE` | 3 trades fallidos consecutivos (ORDER_REJECTED). |
| **L2** | `SERVICE` | Componente Interno | `SELF_HEAL` | Congelamiento de ticks (`Check_Data_Coherence`) o socket caído. |
| **L3** | `GLOBAL` | Ecosistema Completo | `LOCKDOWN` | 3+ activos muteados o pérdida total de ADX (`Check_Veto_Logic`). |

---

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

## 🏛️ E14: Arquitectura de Resiliencia Granular — Especificación Técnica

**Trace_ID**: ARCH-RESILIENCE-ENGINE-V1 | **Épica**: E14 | **Sprint**: 23/24

Esta sección define el contrato arquitectónico completo para la implementación de la Resiliencia Granular. La implementación de código se realiza en HU 10.14 → 10.16.

---

### Principio de Diseño: Degradación Elegante

> **El sistema no es binario. La salud es un espectro.**
>
> Un "estornudo" (spread alto en un activo) no mata al organismo. Un hospital no cierra por una bombilla fundida. El sistema debe aislar el fallo en la capa más baja posible y seguir generando Alpha con los componentes sanos.

**Regla de Escalada**: El `ResilienceManager` **no puede escalar** al nivel superior si el fallo puede ser contenido y sanado en el nivel inferior.

---

### Contrato: `ResilienceInterface` (Clase Abstracta)

Todos los componentes de diagnóstico (`IntegrityGuard`, `AnomalySentinel`, `CoherenceService`) deben implementar este contrato o reportar a través de él. Ubicación: `core_brain/resilience.py`.

```python
# core_brain/resilience.py — Contrato de la Arquitectura Inmunológica

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid


class ResilienceLevel(Enum):
    """Capa de contención del fallo. De menor a mayor impacto."""
    ASSET    = "L0"   # Un solo instrumento
    STRATEGY = "L1"   # Una estrategia específica
    SERVICE  = "L2"   # Un componente interno
    GLOBAL   = "L3"   # Todo el ecosistema


class EdgeAction(Enum):
    """Acción autónoma que el ResilienceManager aplica."""
    MUTE       = "MUTE"       # L0: Ignorar señales del activo afectado
    QUARANTINE = "QUARANTINE" # L1: Detener la estrategia afectada
    SELF_HEAL  = "SELF_HEAL"  # L2: Reiniciar socket / limpiar caché
    LOCKDOWN   = "LOCKDOWN"   # L3: Suspensión total del sistema


class SystemPosture(Enum):
    """Postura operacional global del orquestador."""
    NORMAL   = "NORMAL"   # 100% operativo. L0/L1 limpios.
    CAUTION  = "CAUTION"  # Anomalía local. Cuarentenas activas. Riesgo reducido (0.5%).
    DEGRADED = "DEGRADED" # Fallo L2. Solo gestión de posiciones abiertas. Sin nuevas entradas.
    STRESSED = "STRESSED" # L3 activado. Cierre ordenado. Intervención manual requerida.


@dataclass
class EdgeEventReport:
    """
    Reporte que cualquier componente emite al ResilienceManager.
    El componente NO decide la acción — solo reporta severidad y alcance.
    """
    level:      ResilienceLevel        # Capa afectada (L0-L3)
    scope:      str                    # Identificador del afectado (symbol, strategy_id, service_name, "GLOBAL")
    action:     EdgeAction             # Acción recomendada
    reason:     str                    # Mensaje legible para auditoría
    trace_id:   str = field(default_factory=lambda: f"EDGE-{uuid.uuid4().hex[:8].upper()}")
    metadata:   dict = field(default_factory=dict)


class ResilienceInterface(ABC):
    """
    Contrato obligatorio para componentes de diagnóstico.
    Garantiza que ningún componente decide acciones unilateralmente.
    """

    @abstractmethod
    def check_health(self) -> Optional[EdgeEventReport]:
        """
        Ejecuta el diagnóstico del componente.

        Returns:
            EdgeEventReport si detecta un problema, None si todo está sano.
        """
        ...
```

---

### Protocolo: `ResilienceManager` (El Cerebro Inmunológico)

El `ResilienceManager` es el único árbitro de acciones. Recibe `EdgeEventReport` de todos los componentes y:
1. Aplica la acción del reporte al scope indicado
2. Actualiza la `SystemPosture` global
3. Detecta correlación de fallos para escalar automáticamente
4. Persiste el evento en `sys_audit_logs`

**Diseño (HU 10.15):**

```python
class ResilienceManager:
    def __init__(self, storage: StorageManager): ...

    def process_report(self, report: EdgeEventReport) -> SystemPosture:
        """
        Procesa un EdgeEventReport, aplica la acción y devuelve la
        nueva postura del sistema.

        Flujo:
        1. Registrar el evento
        2. Aplicar EdgeAction al scope
        3. Ejecutar Correlation Engine
        4. Transicionar SystemPosture si aplica
        5. Retornar nueva postura
        """
        ...

    def get_posture(self) -> SystemPosture:
        """Retorna la postura operacional actual (sin I/O)."""
        ...
```

---

### Matriz de Intervención (La "Ley" del ResilienceManager)

Esta tabla es el contrato operacional que vincula la capa de fallo con la postura resultante y la acción automática. **El ResilienceManager no puede decidir fuera de estos límites.**

| Capa de Fallo | Entidad Afectada | Postura Resultante | Acción Automática | Comportamiento del Loop |
|:---|:---|:---|:---|:---|
| **L0** (`ASSET`) | Instrumento (ej. `XAUUSD`) | `CAUTION` | `MUTE`: Ignorar señales del activo. Reducción de riesgo. | Loop continúa. Otros activos operan normalmente. |
| **L1** (`STRATEGY`) | Instancia algorítmica | `CAUTION` | `QUARANTINE`: Detener estrategia afectada. Otras estrategias sanas siguen. | Loop continúa. |
| **L2** (`SERVICE`) | Componente interno (DB, socket) | `DEGRADED` | `SELF_HEAL`: Reintentar hasta 3×. Solo gestión de posiciones abiertas. Sin nuevas entradas. | Loop continúa en modo defensivo. |
| **L3** (`GLOBAL`) | Ecosistema completo | `STRESSED` | `LOCKDOWN`: Cancelar órdenes, SL → Breakeven, broadcast operador. Intervención manual requerida. | Loop se detiene (`_shutdown_requested = True`). |

> **Regla de Oro**: Solo `STRESSED` (L3) detiene el loop. `DEGRADED`, `CAUTION` y escaladas intermedias degradan el comportamiento sin interrumpir la operatividad.

#### Umbrales del Heartbeat (OEM Check #9)

El check `_check_orchestrator_heartbeat()` opera con su propia nomenclatura interna de check (`OK/WARN/FAIL`), separada de la `SystemPosture`. El `ResilienceManager` interpreta el resultado del check y decide la postura:

| Gap del Heartbeat | Resultado del Check | Postura que aplica ResilienceManager |
|:---|:---|:---|
| `< 10 min` | `OK` | `NORMAL` (sin cambio) |
| `10 – 20 min` | `WARN` | `CAUTION` (alerta, loop continúa) |
| `> 20 min` | `FAIL` | `DEGRADED` (fallo L2, modo defensivo) |
| Fallo de persistencia | `FAIL` + escalada | `STRESSED` si correlaciona con L2 adicional |

---

### Motor de Correlación de Fallos

**Problema**: La granularidad tiene un riesgo. Un L0 individual es ruido; tres L0 simultáneos pueden ser el inicio de un colapso sistémico.

**Reglas de Escalada Automática:**

| Condición de Correlación | Acción Automática |
|:---|:---|
| ≥ 3 activos en `L0: MUTE` simultáneamente | Escalar a `L3: GLOBAL LOCKDOWN` |
| ≥ 2 estrategias en `L1: QUARANTINE` en < 5 min | Transición a `DEGRADED` + alerta |
| `L2: SELF_HEAL` falla 3 veces seguidas | Escalar a `L3: GLOBAL LOCKDOWN` |
| `SystemPosture` en `DEGRADED` > 30 min sin recovery | Notificar al operador + mantener DEGRADED |

**Ventana de correlación:** Los eventos se evalúan en una ventana deslizante de **5 minutos**.

---

### Refactor del `MainOrchestrator` (HU 10.15)

**Estado Actual (problema):**
```python
# Cada gate toma la decisión unilateralmente
if health.overall == HealthStatus.CRITICAL:
    self._shutdown_requested = True   # ← "Mazazo"
    break
```

**Estado Objetivo (resiliencia granular):**
```python
# El componente reporta. El ResilienceManager decide.
report = self.integrity_guard.check_health()
if report:
    new_posture = self.resilience_manager.process_report(report)
    if new_posture == SystemPosture.STRESSED:
        break  # Solo L3 detiene el loop
    # L0/L1/L2: el loop continúa con postura degradada
```

**Mapeo de Gates actuales → ResilienceInterface:**

| Gate Actual | Nivel | Comportamiento Nuevo |
|:---|:---|:---|
| `IntegrityGuard` CRITICAL → shutdown | `L2/L3` | `L2` → DEGRADED (loop continúa). `L3` → STRESSED (shutdown). |
| `AnomalySentinel` LOCKDOWN → shutdown | `L0/L3` | Flash Crash 1 activo → `L0: MUTE`. Flash Crash sistémico → `L3: LOCKDOWN`. |
| `CoherenceService` VETO → quarantine | `L1` | Ya funciona por estrategia. Integrar con `ResilienceManager`. |

---

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
- [x] **HU 10.6: AutonomousSystemOrchestrator — Diseño FASE4** ✅ (24-Mar-2026)
- [x] **Sprint 23: EDGE Reliability — HU 10.10 + HU 10.11** ✅ (27-Mar-2026)
  - HU 10.10: OEM integrado en producción con `shadow_storage` inyectado
  - HU 10.11: 9° check `orchestrator_heartbeat` + `last_results` expuesto vía API
  - Endpoint `GET /api/system/health/edge` + UI `SystemHealthPanel`
- [ ] **HU 10.12**: Timeout guards en `run_single_cycle()` (Sprint 23)
- [ ] **HU 10.13**: Contract tests para bugs conocidos (Sprint 23)
- [ ] **HU 10.14**: `ResilienceInterface` + modelos de datos en `core_brain/resilience.py` (Sprint 23)
- [ ] **HU 10.15**: `ResilienceManager` + refactor `MainOrchestrator` (Sprint 24)
- [ ] **HU 10.16**: Self-Healing Engine + Correlation Engine (Sprint 24)
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
