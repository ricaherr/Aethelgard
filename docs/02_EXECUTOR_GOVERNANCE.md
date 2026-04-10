# Dominio 02: EXECUTOR_GOVERNANCE (Risk & Execution Sovereignty)

**ID de Transacción:** JOB-02-EXECUTOR-GOVERNANCE-2026-04-10
**Fecha:** 10 de abril de 2026

## 🎯 Propósito
Consolidar la gestión de riesgo y la ejecución de órdenes bajo un esquema holístico de "Soberanía Operativa". Este dominio define cómo el sistema protege el capital y administra el ciclo de vida de una orden, garantizando que el riesgo (Unidades R) y la ejecución (Conectores/Vetos) operen de forma sinérgica e independiente de las limitaciones individuales de cada broker.

## 📐 Filosofía de Capital: Unidades R

Aethelgard no opera bajo la noción de lotes absolutos por activo, sino que administra **Volatilidad Normalizada**. 

*   **Fórmula Base**: `Lots = Risk_USD / (SL_Dist * Contract_Size)`
*   **Aritmética**: Es obligatorio el uso del tipo `Decimal` nativo de Python para garantizar precisión institucional y anular desviaciones de punto flotante.
*   **Normalización (SSOT)**: La tabla `asset_profiles` actúa como la única fuente de verdad para parámetros como el *tick size* y *contract size*, manteniendo a `core_brain` agnóstico respecto a la procedencia de los datos.

## 🚀 Motor de Ejecución Agnóstico

La arquitectura del sistema garantiza la neutralidad frente a los corredores. El cálculo de riesgo y la intención de orden suceden de forma abstracta; el conector (`connectors/`) simplemente traduce la instrucción matemática final al protocolo específico del proveedor de liquidez.

### Protocolos de Conexión

1. **cTrader Open API (Prioridad: 100 - Primario FOREX)**: Conector WebSocket nativo asíncrono (sin dependencia de DLL). Validado a través de credenciales centralizadas en la tabla `sys_data_providers`.
2. **MetaTrader 5 (MT5)**: Conexión de alta fidelidad (Prioridad 70) vía integración local en Python. Actúa como fallback primario para Forex y CFDs institucionales.
3. **FIX / CCXT / Data APIs**: Soluciones escalables para entornos institucionales y puentes directos hacia criptomonedas y parqués estructurados (Alpha Vantage, Yahoo Finance, etc.).

## 🛡️ Matriz de Veto Adaptativo

El paso entre la generación de la señal y la ejecución real está protegido por vetos automáticos para mitigar la ineficiencia de ejecución:

*   **Slippage Controller**: Veto técnico que anula la ejecución si la discrepancia matemática entre el precio de señal (teórico) y el precio final del libro de órdenes excede el margen configurado (default: 2.0 pips).
*   **Spread Validation**: Detección de ensanchamientos anormales del *spread* en ventanas no líquidas o de pre-noticia, cancelando preventivamente la intención de entrada.
*   **Volatility Veto (Z-Score)**: Frena la operatividad si la volatilidad en tiempo real (medida en desviaciones estándar sobre un período) supera los umbrales seguros configurados (ej. `> 3.0` Z-Score).

## 🚨 Anomaly Sentinel (Protocolos de Lockdown)

El sistema actúa con autonomía preventiva ante eventos macroeconómicos adversos (Cisnes Negros) a través del **Anomaly Sentinel**.

### Umbrales y Reacciones
Basado en parámetros dinámicos (`dynamic_params.json`):
*   **Flash Crash**: Caídas abruptas (ej. `< -2.0%` en una sola vela).
*   **Volatility Spike**: Z-Score de volatilidad extrema persistente (mínimo 3 velas).
*   **Volume Spike**: Volumen transaccional por encima del percentil 90 histórico.

### Estados de Salud Integrados
1. **NORMAL**: Sistema en flujo operativo regular (100% de capital autorizado por señal).
2. **CAUTION**: Reducción precautoria del riesgo por trade (50% de recorte de capital).
3. **DEGRADED**: Lockdown Preventivo. Múltiples anomalías impiden nuevas entradas; el enrutamiento permite exclusivamente el cierre de posiciones abiertas (riesgo en OFF).
4. **STRESSED**: Evento extremo validado. Protocolo de bloqueo estricto con:
   * Cancelación de órdenes pendientes.
   * Ajuste sistemático de *Stop Losses* a *Breakeven* para proteger el balance.
   * Registro del evento anómalo trazado (Trace_ID único `BLACK-SWAN-{UUID}`).

## 🔁 Cooldown Management: Resiliencia de Ejecución

Ante fallos durante el enrutamiento o confirmación del broker, Aethelgard nunca aplica fuerza bruta. 

*   **Modelo Exponencial**: Se implementa una progresión de reintento exponencial basado en `ExecutionFailureReason` (Ej. Liquidez insuficiente = 5 min → 10 min → 15 min).
*   **Ajuste por Volatilidad**: Los *cooldowns* se auto-escalan ponderados por la volatilidad actual, asumiendo que un entorno estresado necesita más tiempo para estabilizar la contraparte líquida del libro de órdenes.

## 🗄️ Technical Specs (SSOT Tables)

Para auditoría exhaustiva y transparencia de gobernanza técnica, este dominio empodera las siguientes tablas del sistema:

*   `asset_profiles`: Base agnóstica para cálculo global de posiciones y valores de tick.
*   `sys_cooldown_tracker`: Trazabilidad inmutable de rechazos, tipos de fallo en ejecución y periodos de restricción (`next_allowed_retry`).
*   `anomaly_events`: Histórico consolidado de picos de volatilidad, caídas y ejecuciones del Anomaly Sentinel.
*   `execution_shadow_logs`: Auditoría de alta fidelidad que registra métricas sobre slippage y latencia para reportes institucionales.

---
**Nota del Documentador:** *La consolidación de reglas define al módulo de ejecución (Executor) como una muralla de validación implacable, negando rotundamente comprometer el capital de la cuenta si el riesgo normativo o la calidad de la liquidez no están alineados con los estándares de Aethelgard.*