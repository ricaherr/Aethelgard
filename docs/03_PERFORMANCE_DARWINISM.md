# Dominio 03: PERFORMANCE_DARWINISM (Shadow, Rankings & Coherencia)

**ID de Transacción:** JOB-03-PERFORMANCE-DARWINISM-2026-04-10  
**Fecha:** 10 de abril de 2026

## 🎯 Propósito
Maximizar el rendimiento ajustado al riesgo mediante la meritocracia matemática. Toda estrategia en Aethelgard es sometida al **Darwinismo Algorítmico**, evaluando su valía primero en entornos virtuales rigurosos y monitoreando continuamente que sus resultados financieros reales mantengan una **Coherencia Matemática** estricta frente a sus premisas teóricas iniciales.

---

## 🧬 Tesis del Darwinismo Algorítmico (Ciclo de Vida)

El sistema jamás asume que un backtest exitoso equivale a rentabilidad real. Las estrategias atraviesan obligatoriamente un ducto de maduración de tres estados:

1. **Monitor (SHADOW)**: Fase de incubación. La estrategia ejecuta en el mercado en vivo pero bajo un esquema simulado que internaliza las fricciones reales del broker (latencias, slippages). 
2. **Active (LIVE)**: Promoción a capital real. El sistema le otorga margen de operatividad solo si demuestra resiliencia frente al entorno real durante la etapa SHADOW.
3. **Quarantine (DISABLED)**: Suspensión inmediata y degradación autónoma del sistema si la estrategia comienza a fallar, entra en una racha de *Drawdown* crítico o viola los umbrales de deriva técnica.

---

## 🌑 Shadow Reality Engine

Para evitar el espejismo del *paper trading* convencional, el **Shadow Reality Engine** actúa como un inyector de *fricción*:
*   Penaliza el rendimiento teórico de una estrategia virtual restándole el slippage estimado basado en el spread dinámico en tiempo real y perfiles de liquidez (`asset_profiles`).
*   Inyecta penalidades de latencia imitando la infraestructura real.
*   Registra esta "realidad degradada" en las métricas de sombra para que el Ranker evalúe el desempeño real esperado.

---

## 📐 Métricas de Coherencia (Drift)

La **Coherencia Matemática** responde a la pregunta algorítmica: *"¿El modelo sigue comportándose según su expectativa teórica o la fricción del mercado lo está destruyendo?"*

*   **Cálculo de Degradación (Drift)**:
    `Degradation = (Theoretical Sharpe - Real Sharpe) / Theoretical Sharpe`
*   **Varianza de Ejecución (Slippage)**:
    Se calcula la volatilidad de los *slippages* registrados (en pips/ticks) usando desviación estándar. Alta varianza indica infraestructura inestable o manipulación del broker.

**Estados de Coherencia**:
*   🟢 **COHERENT** (≥80% Score + <15% Degradation): Continúa operando con normalidad.
*   🟡 **MONITORING** (≥80% Score + ≥15% Degradation): Opera, pero levanta alertas de precaución a la UI (elevated caution).
*   🔴 **INCOHERENT** (<80% Score): Se dispara inmediatamente un **Veto de Coherencia**.

---

## ⚖️ Protocolo de Promoción y Degradación (Veto Link)

El `Strategy Ranker` es el árbitro final de estado, utilizando métricas cruzadas estrictas (Ranker + Coherencia):

### Para Promoción (SHADOW → LIVE)
*   **Profit Factor (PF)**: `> 1.5` sostenido en condiciones de simulación con inyección de coste.
*   **Trade Count**: Mínimo de trades estadísticamente significativos (Ej. 50 trades válidos en un mes).

### Para Degradación y Veto (LIVE → QUARANTINE)
*   **Drawdown (DD)**: Si el Drawdown máximo excede el `3.0%`.
*   **Veto de Coherencia (<80%)**: Si el `CoherenceService` marca el estado como *INCOHERENT*, emite un flag `veto_new_entries = True` directamente hacia el `RiskManager` (Dominio 02). **El Executor entonces bloquea de forma autónoma cualquier nueva entrada** y orquesta la liquidación de las posiciones vigentes para preservar capital, escalando el mercado desde la base algorítmica.

---

## 🎯 Ciclo BACKTEST → SHADOW: Umbral Adaptativo (Estado Real)

**Vigente desde:** 2026-04-13 | Trace_ID: EDGE-STRATEGY-SSOT-SYNC-2026-04-13

> La documentación anterior indicaba que la promoción BACKTEST → SHADOW usaba un threshold fijo de 0.75. **Esta sección corrige ese dato.**

### Umbral de Promoción (promotion_threshold)

El threshold de promoción es **adaptativo y persistido por estrategia** en `sys_strategies.execution_params`:

```json
{
  "promotion_threshold": 0.68,
  "consecutive_failures": 2
}
```

| Campo | Significado |
|---|---|
| `promotion_threshold` | Umbral actual para promover a SHADOW. Inicia en `MIN_REGIME_SCORE` (0.75) |
| `consecutive_failures` | Número de backtests sin superar el threshold (relajación progresiva) |

### Reglas de evolución

- **Bootstrap:** Si no existe `promotion_threshold` en `execution_params`, se usa `backtester.MIN_REGIME_SCORE` (0.75).
- **Persistencia:** Tras cada run del `BacktestOrchestrator`, el threshold efectivo se guarda en `execution_params`.
- **Relajación:** Con `consecutive_failures >= 3`, el threshold baja un 5% (`threshold × 0.95`) para desbloquear estrategias bloqueadas crónicamente.
- **No se permite floor de 0.0:** La relajación progresiva no persiste valores sin base empírica.

### Fuente de verdad

`sys_strategies.execution_params` es el SSOT del threshold. No existe valor fijo en código.

## 🗄️ Data Schema (SSOT)

Auditoría inmutable para análisis algorítmico:

*   `sys_signal_ranking`: Almacena permanentemente el *score*, el *Profit Factor*, y el *Drawdown* de cada versión de estrategia, determinando quién recibe capital (`status: LIVE|SHADOW|QUARANTINE`).
*   `sys_coherence_logs` (`coherence_events` / `execution_shadow_logs`): Trazabilidad de la divergencia, guardando el precio teórico vs. el precio real de llenado, la latencia (ms) de ida y vuelta, y el respectivo dictamen (*COHERENT / INCOHERENT*), referenciado con un `trace_id` único para auditoría transparente.