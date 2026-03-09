# Dominio 04: RISK_GOVERNANCE (Unidades R, Safety Governor, Veto, Anomaly Sentinel)

## 🎯 Propósito
Garantizar la preservación del capital mediante una gestión de riesgo de nivel institucional, basada en la normalización universal de activos, la soberanía de intervención humana y la detección/neutralización autónoma de eventos extremos (Cisnes Negros).

## 🚀 Componentes Críticos
*   **Universal Risk Manager**: Motor de cálculo basado en Unidades R que garantiza un riesgo constante en USD independientemente del activo. Evalúa el contexto (FVG/Order Blocks) emitiendo advertencias de probabilidad mitigada `[CONTEXT_WARNING]` sin interrumpir la operación.
*   **Sovereignty Gateway**: Matriz de permisos que define la autonomía del sistema por componente o mercado.
*   **Anomaly Sentinel (HU 4.6)**: Motor de detección de volatilidad extrema y Flash Crashes que activa protocolos defensivos instantáneos (Lockdown Preventivo, cancelación de órdenes, cierre de posiciones).
*   **Circuit Breakers**: Bloqueos automáticos por drawdown o fallos consecutivos.

## 📐 Filosofía de Cálculo: Unidades R
Aethelgard no opera instrumentos, sino **Volatilidad Normalizada**. 
*   **Fórmula**: `Lots = Risk_USD / (SL_Dist * Contract_Size)`
*   **Aritmética**: Uso obligatorio de `Decimal` para precisión financiera.
*   **Normalización**: Tabla `asset_profiles` como fuente única de verdad para tick sizes y contract sizes.

## 🛡️ ANOMALY SENTINEL (HU 4.6) — Protocolo de Defensa Automática

### Umbrales Críticos (SSOT desde `dynamic_params.json`)
| Parámetro | Valor | Significado |
|---|---|---|
| `volatility_zscore_threshold` | 3.0 | Volatilidad > 3 desviaciones estándar = Anomalía |
| `flash_crash_threshold` | -2.0% | Caída > 2% en una vela = Flash Crash |
| `anomaly_lookback_period` | 50 velas | Ventana de cálculo para Z-Score |
| `anomaly_persistence_candles` | 3 velas | Anomalía debe persistir en N velas para activar defensa |
| `volume_spike_percentile` | 90 | Volumen > 90p de la distribución histórica |

### Estados de Salud Integrados (NORMAL → STRESSED)
El sistema transita automáticamente entre estos estados basándose en anomalías detectadas:

1. **NORMAL** (0 anomalías recientes)
   - Sistema operativo en condiciones estables
   - Todas las estrategias activas
   - Riesgo por trade: 1% del capital (configuración estándar)

2. **CAUTION** (1-2 anomalías en últimas 50 velas)
   - Señal de prudencia: mercado mostrando signos de estrés
   - Estrategias operativas pero con tamaño reducido
   - Riesgo por trade: 0.5% (reducción 50%)
   - UI: BadgeAmarillo + Alerta proactiva

3. **DEGRADED** (3+ anomalías en últimas 50 velas O drawdown > 15%)
   - Sistema bajo presión: múltiples señales de riesgo sistémico
   - Ejecución de órdenes PAUSADA (solo cierre de posiciones)
   - Nuevas entradas: BLOQUEADAS
   - Lockdown Preventivo: Activado
   - UI: BadgeRojo + [RISK_PROTOCOL_ACTIVE]

4. **STRESSED** (Anomalía crítica detectada O drawdown > 20%)
   - Evento extremo: comportamiento no histórico
   - Sistema en defensa total
   - Cancelación automática de órdenes pendientes
   - Stop Losses → Breakeven (protección de pérdidas)
   - Broadcast de [ANOMALY_DETECTED] al operador
   - UI: Thought Console con sugerencia de intervención manual

### Protocolo Defensivo Automático (Lockdown)
**Trigger**: `volatility_zscore > 3.0` O `flash_crash < -2%` + anomalía persiste 3 velas

**Acciones Ejecutadas (Orden Estricto)**:
1. ✅ Activar modo Lockdown (`RiskManager.activate_lockdown()`)
2. ✅ Cancelar órdenes pendientes (`RiskManager.cancel_pending_orders()`)
3. ✅ Ajustar Stops a Breakeven (`PositionManager.adjust_stops_to_breakeven()`)
4. ✅ Transitar salud a DEGRADED/STRESSED
5. ✅ Persistir evento en DB con `trace_id` único (BLACK-SWAN-{UUID})
6. ✅ Broadcast de [ANOMALY_DETECTED] + contexto a WebSocket
7. ✅ Generar sugerencia en Thought Console

**Reversión**: Manual del operador o cuando anomalía desaparece + N velas sin estrés

### Persistencia de Anomalías (Trace_ID & Auditabilidad)
```
anomaly_events (table)
├── trace_id: str (BLACK-SWAN-{uuid})
├── symbol: str
├── anomaly_type: enum [VOLATILITY_SPIKE, FLASH_CRASH, VOLUME_SPIKE, CONSECUTIVE_LOSSES]
├── severity: enum [LOW, MEDIUM, HIGH, CRITICAL]
├── zscore: float (si aplica)
├── pct_change: float (si aplica)
├── candle_time: datetime
├── action_taken: str
├── timestamp: datetime
└── Índices: (symbol, timestamp), (trace_id), (severity)
```

## 🖥️ UI/UX REPRESENTATION
*   **Master Veto Panel**: Consola de control con toggles de seguridad institucional para habilitar/deshabilitar autonomía por mercado.
*   **Exposure Heatmap**: Dashboard visual que muestra el riesgo agregado del portafolio y la proximidad al Hard Drawdown.
*   **Sentient Thought Console**: Feed de pensamientos con tags `[ANOMALY_DETECTED]` y sugerencias proactivas de intervención (activación manual de defensas, espera de estabilización, etc.).
*   **Anomaly History Widget**: Vista histórica de eventos extremos con filtros por símbolo, tipo, severidad y traza (Trace_ID).

## 📈 Roadmap del Dominio
- [ ] Implementación del Sovereignty Gateway Manager.
- [x] Despliegue del Safety Governor y Veto granular.
- [x] Despliegue de Drawdown Monitors multi-tenant.
- [x] **Integración del Anomaly Sentinel (Antifragility Engine) — HU 4.6 COMPLETADA** ✅
  - Z-Score detector operativo
  - Flash Crash detector operativo
  - Protocolo Lockdown automático
  - Thought Console + sugerencias inteligentes
  - Integración con Health System (NORMAL/CAUTION/DEGRADED/STRESSED)
  - Base de datos de anomalías con Trace_ID

