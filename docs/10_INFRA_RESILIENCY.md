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
- [ ] HU 10.6: AutonomousSystemOrchestrator — Diseño e implementación (FASE4).
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
| `OperationalEdgeMonitor` | `core_brain/operational_edge_monitor.py` | 8 invariantes de negocio |
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

