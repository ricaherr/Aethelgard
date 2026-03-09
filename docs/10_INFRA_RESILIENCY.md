# Dominio 10: INFRA_RESILIENCY (Health, Self-Healing, Anomaly Integration)

## 🎯 Propósito
Garantizar la operatividad perpetua del sistema mediante una infraestructura auto-sanable, monitoreo proactivo de signos vitales y una gestión eficiente de recursos técnicos. Coordinar la respuesta automática a anomalías sistémicas (volatilidad extrema, flash crashes) para transición segura entre estados de salud.

## 🚀 Componentes Críticos
*   **Autonomous Heartbeat**: Sistema de monitoreo de signos vitales que detecta hilos congelados o servicios caídos.
*   **Auto-Healing Engine**: Protocolos de recuperación automática que reinician servicios o resincronizan estados tras detectar fallos.
*   **Resource Sentinel**: Monitor de consumo de CPU, memoria y espacio en disco con alertas de umbral.
*   **Log Management (Linux Style)**: Sistema de rotación diaria con retención estricta de 15 días para optimizar el almacenamiento.
*   **PaperConnector (Hybrid Safety)**: Entorno de simulación de alta fidelidad que desacopla el riesgo financiero del riesgo de infraestructura durante fases de calibración o fallos de red críticos.
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
- [ ] Implementación de orquestación de servicios en contenedores aislados.
- [ ] Integración de meta-aprendizaje sobre recursos técnicos.

