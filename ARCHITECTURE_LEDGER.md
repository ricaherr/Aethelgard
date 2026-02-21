# AETHELGARD ARCHITECTURE LEDGER
> **Única Fuente de Verdad Arquitectónica**
> **Fecha de Creación:** 2026-02-18
> **Estado:** VIVO

---

## 1. 🎯 Estado de la Misión: Aethelgard EDGE
Aethelgard no es un simple bot de trading; es un **Sistema de Hedge Fund Autónomo (EDGE)**.
Su misión es operar de forma **autónoma, agnóstica y antifrágil** en múltiples mercados simultáneamente.
No busca la "estrategia perfecta", sino que gestiona un **Ecosistema de Estrategias** que compiten entre sí (Darwinismo Algorítmico) para sobrevivir y operar capital real solo cuando demuestran adaptación al régimen actual.

## 2. 🏗️ Arquitectura Validada: El Flujo de la Verdad
El flujo de datos es unidireccional, estricto y auditable.

```mermaid
graph TD
    A[Scanner Proactivo] -->|Datos OHLC| B(Regime Classifier);
    B -->|Contexto de Mercado| C{Signal Factory};
    C -->|Estrategias (Velez, Trifecta...)| D[Shadow Engine];
    D -->|Señales Ponderadas| E{Jurado de Estrategias};
    E -->|Veredicto: REAL| F[Risk Manager];
    E -->|Veredicto: VIRTUAL| G[Virtual Recorder];
    F -->|Aprobado| H[Executor (Trace_ID)];
    F -->|Vetado| G;
    H -->|Ejecución| I[Omnichain Router];
    I -->|Normalización| J[Broker Connectors];
```

## 6. 🛡️ Ley de Agnosticismo (Omnichain Law)
El **Core Brain** es sagrado y debe permanecer puro. Queda terminantemente **PROHIBIDO** importar librerías de terceros vinculadas a brokers específicos (ej. `MetaTrader5`, `OANDA`, `ccxt`) dentro de cualquier módulo que no resida en la carpeta `connectors/`.

## 9. 🔒 Ley de Fidelidad de Fuente (Source Fidelity Law)
En mercados descentralizados (Forex, Crypto), la fuente de análisis y la fuente de ejecución son una unidad indivisible para garantizar la veracidad del sistema.
- **Regla**: Si el mercado es `DECENTRALIZED`, el `OrderExecutor` rechazará cualquier señal cuya `provider_source` no coincida exactamente con el conector de ejecución activo.

## 7. 🏗️ Estructura de 3 Capas
Para asegurar la escalabilidad "Aethelgard Omnichain", el flujo de conectividad se divide en:
1.  **Capa de Estrategia (Brain)**: Define el "Qué" y el "Cuándo". No sabe dónde se ejecuta.
2.  **Capa de Router (Orchestrator)**: Gestiona el "Dónde". Decide qué proveedor es óptimo para la orden actual.
3.  **Capa de Provider (Connector)**: Traduce el "Cómo". Habla el idioma específico de cada broker.

## 8. ⌚ Estándar Cronológico Universal
Para evitar desajustes en backtesting y ejecución real entre proveedores de distintas zonas horarias:
- Toda la data temporal en Aethelgard se procesa y almacena en **UTC ISO 8601** (`YYYY-MM-DDTHH:MM:SSZ`).
- Los conectores son responsables de traducir el tiempo local del broker a UTC antes de entregar el dato al orquestador.


### Componentes Clave:
1.  **ScannerEngine**: Proactivo, multihilo, vigila activos sin esperar ticks.
2.  **RegimeClassifier**: Determina el terreno de juego (TREND, RANGE, VOLATILE).
3.  **SignalFactory**: Genera señales puras basadas en lógica técnica.
4.  **Shadow Engine / Jurado**: La nueva capa de inteligencia que decide si una señal merece riesgo real o solo seguimiento virtual.
5.  **Risk Manager**: El guardián final del capital (Drawdown, Exposición).
6.  **Executor**: Ejecuta y registra con trazabilidad total (`Trace_ID`).

## 3. 🧠 Definiciones Estratégicas

### El Jurado de Estrategias (The Jury)
Es el mecanismo de decisión que reemplaza a las reglas estáticas.
- **Función**: Evaluar la "probabilidad de éxito" de una señal basándose en el rendimiento reciente (Shadow Performance) de la estrategia emisora en el régimen actual.
- **Veredicto**:
    - **REAL**: La estrategia está "Hot" (Profit Factor > 1.5 en últimas 24h). Pasa al Risk Manager.
    - **VIRTUAL**: La estrategia está "Cold" o en "Cuarentena". Se registra en `virtual_trades` para seguimiento.

### Las 3 Capas de Confluencia
1.  **Capa 1: Contexto (El Mapa)**
    - ¿Dónde estamos? (Tendencia, Rango, Pánico).
    - Definido por `RegimeClassifier`.
2.  **Capa 2: Táctica (La Jugada)**
    - ¿Qué setup tenemos? (Elephant Candle, Trifecta, RSI Divergence).
    - Definido por `Strategies`.
3.  **Capa 3: Liquidez (El Combustible)**
    - ¿Hay gasolina? (Volumen, Spread, Horario).
    - Definido por `LiquidityFilter` (Future implementation).

## 4. 👻 Protocolo Shadow: Reglas de Promoción y Degradación

### Estado de Estrategia
Cada estrategia tiene un estado por activo/timeframe:
- 🟢 **ACTIVE (REAL)**: Opera con capital real.
- 🟡 **MONITOR (SHADOW)**: Opera en virtual, candidata a promoción.
- 🔴 **QUARANTINE (DISABLED)**: Rendimiento pobre, degradada a virtual.

### Reglas de Transición
1.  **Promoción (Monitor -> Active)**:
    - **Win Rate Virtual (24h)**: > 55%
    - **Profit Factor Virtual**: > 1.5
    - **Trades Mínimos**: 5 operaciones virtuales positivas consecutivas o consistencia en 20 trades.
2.  **Degradación (Active -> Quarantine)**:
    - **Drawdown Real**: > 3% del capital asignado a la estrategia.
    - **Racha Perdedora**: 3 pérdidas consecutivas (Lockdown específico de estrategia).
    - **Drift de Régimen**: La estrategia opera mal en el nuevo régimen detectado.

## 5. 📜 Log de Decisiones Arquitectónicas

| Fecha | Decisión | Motivo | Impacto |
| :--- | :--- | :--- | :--- |
| **2026-02-18** | **Creación del Shadow Portfolio** | Necesidad de validar estrategias sin arriesgar capital ("Forward Testing"). | Creación de tabla `virtual_trades` y lógica de ejecución dual. |
| **2026-02-18** | **Separación REAL vs VIRTUAL** | Evitar contaminación de métricas de PnL real. | Campo `execution_mode` en todas las señales. |
| **2026-02-18** | **Estrategia Universal via Engine** | Flexibilidad para añadir reglas sin código. | Preparación para futuro `JSON Strategy Engine`. |

---
*Este documento es la ley técnica de Aethelgard. Cualquier cambio en la lógica core debe ser registrado aquí.*
