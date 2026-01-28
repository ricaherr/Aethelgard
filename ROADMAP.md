# Aethelgard – Roadmap

Resumen del roadmap de implementación. Detalle completo en [AETHELGARD_MANIFESTO.md](AETHELGARD_MANIFESTO.md#roadmap-de-implementación).

---

## Fase 1: Infraestructura Base ✅ COMPLETADA

- Servidor FastAPI + WebSockets, RegimeClassifier, Storage, conectores (NT8, MT5, TV), Tuner.

---

## Fase 1.1: Escáner Proactivo Multihilo ✅ COMPLETADA (Enero 2026)

**Objetivo:** Escáner proactivo que obtiene datos de forma autónoma y escanea múltiples activos en paralelo.

**Implementado:**

| Componente | Descripción |
|------------|-------------|
| `core_brain/scanner.py` | `ScannerEngine`, `CPUMonitor`, protocolo `DataProvider`. Multithreading con `concurrent.futures`. |
| `connectors/mt5_data_provider.py` | OHLC vía `mt5.copy_rates_from_pos` (sin gráficas abiertas). |
| `config/config.json` | `assets`, `cpu_limit_pct`, `sleep_*_seconds`, `mt5_*`, etc. |
| `RegimeClassifier.load_ohlc()` | Carga masiva OHLC para el escáner. |
| `run_scanner.py` / `test_scanner_mock.py` | Entrypoint con MT5 y test con mock. |

**Funcionalidades:** Lista de activos configurable, un clasificador por símbolo, escaneo en hilos, control de CPU (aumento de sleep si CPU > umbral), priorización TREND/CRASH 1 s, RANGE 10 s, NEUTRAL 5 s.

---

## Fase 2: Estrategias Modulares ✅ PARCIALMENTE COMPLETADA

**Objetivo:** Implementar estrategias de trading basadas en Oliver Vélez con activación por régimen.

### ✅ Fase 2.1: Signal Factory y Lógica de Decisión Dinámica (Enero 2026)

**Implementado:**

| Componente | Descripción |
|------------|-------------|
| `core_brain/signal_factory.py` | Motor de generación de señales con estrategia Oliver Vélez |
| Sistema de Scoring | Evaluación 0-100: +30 TREND, +20 Vela Elefante, +20 Volumen, +30 SMA20 |
| Filtrado por Membresía | FREE (0-79), PREMIUM (80-89), ELITE (90-100) |
| `models/signal.py` | Actualizado con campos `score`, `membership_tier`, indicadores de calidad |
| `connectors/bridge_mt5.py` | Auto-ejecución en Demo, tracking de `signal_results` |
| `example_live_system.py` | Sistema completo integrado: Scanner + Signal Factory + MT5 |
| `test_signal_factory.py` | Suite de tests para verificar scoring y componentes técnicos |

**Funcionalidades:**
- ✅ Generación de señales BUY/SELL basadas en Oliver Vélez
- ✅ Detección de Velas Elefante (momentum alto: rango > 2x ATR)
- ✅ Análisis de volumen relativo (vs promedio 20 períodos)
- ✅ Proximidad a SMA 20 como zona de rebote (±1%)
- ✅ Cálculo automático de SL/TP (Risk/Reward 1:2)
- ✅ Ejecución automática en MT5 Demo (seguridad verificada)
- ✅ Sistema de membresías para filtrado de señales
- ✅ Batch processing para múltiples símbolos

**Estrategias Implementadas:**
- ✅ **Trend Following**: Operar en TREND, rebote en SMA 20, confirmación volumen
- 🔜 **Range Trading**: Pendiente (operar en RANGE)
- 🔜 **Breakout**: Pendiente (transiciones de régimen)

### 🚧 Fase 2.2: Arquitectura y Estrategias Avanzadas (Prioridad Alta)

**Implementado:**
- ✅ **Refactorización a Patrón Strategy**: Arquitectura modular implementada. `SignalFactory` actúa como orquestador de `strategies/oliver_velez.py`.

**Pendiente de Implementación:**
- **Gestión de Riesgo de Portafolio**: Control de correlación y exposición global.

**Pendiente de Implementación:**
- Range Trading completo
- Breakout Trading en transiciones
- Módulos de estrategias independientes

---

## Fase 3: Feedback Loop y Aprendizaje 🔜 SIGUIENTE

- **Motor de Backtesting Rápido**: Simulación de ejecución del `Scanner` sobre datos históricos para validación pre-live.
- **Feedback de resultados**: Aprendizaje por refuerzo básico y ajuste de pesos.
- **Dashboard de métricas**: Visualización avanzada de KPIs de aprendizaje.

---

## Fase 4: Evolución Comercial 🎯 FUTURA

- **Seguridad SaaS**: Autenticación vía API Key para endpoints HTTP/WebSocket.
- **Multi-tenant**: Soporte para múltiples usuarios aislados.
- **Módulos bajo demanda**: Activación de features vía licencia.
- **Notificaciones**: Integración profunda con Telegram/Discord.

---

*Fuente de verdad: [AETHELGARD_MANIFESTO.md](AETHELGARD_MANIFESTO.md).*
