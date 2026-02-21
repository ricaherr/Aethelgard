# AETHELGARD: 04 PORTFOLIO MANAGEMENT

## 📊 Gestión de Portafolio y Posiciones
Monitoreo de exposición en tiempo real, reconciliación y aprendizaje EDGE.

---

### 📈 Monitoreo de Trades
- **Trade Closure Listener**: Sincronización 1:1 entre MT5 y Base de Datos.
- **P&L Real-Time**: Rastreo de ganancias y pérdidas latentes.
- **Status Sync**: Actualización instantánea del ciclo de vida de la señal.
- **Shadow Portfolio**: Seguimiento de señales virtuales para validación de estrategias sin riesgo de capital (Forward Testing).

---

### 👻 Protocolo Shadow
- 🟢 **ACTIVE (REAL)**: Profit Factor > 1.5 en últimas 24h.
- 🟡 **MONITOR (SHADOW)**: Estrategia en "Forward Testing" para validación.
- 🔴 **QUARANTINE (DISABLED)**: Drawdown > 3% o racha perdedora significativa.

---

### 🧠 Edge Intelligence
- **Feedback Loop**: Comparación de decisiones vs resultados de mercado (5, 10, 20 velas tras salida).
- **EdgeTuner**: Optimización autónoma de filtros basada en la historia del portafolio.
- **Coherence Monitor**: Detección de discrepancias matemáticas entre la señal teórica y la ejecución real.

---

### 📉 Performance Metrics
El dashboard de Portfolio muestra el **Sharpe Ratio**, **Drawdown Histórico** y el **Win Rate** ajustado por régimen de mercado.
