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

## Fase 2: Estrategias Modulares 🚧 EN PROGRESO

- Oliver Vélez (Trend Following, Range, Breakout), gestión de riesgo dinámica, activación por régimen.

---

## Fase 3: Feedback Loop y Aprendizaje 🔜 SIGUIENTE

- Feedback de resultados, aprendizaje por refuerzo básico, dashboard de métricas.

---

## Fase 4: Evolución Comercial 🎯 FUTURA

- Multi-tenant, módulos bajo demanda (API Key), notificaciones (Telegram/Discord), web dashboard.

---

*Fuente de verdad: [AETHELGARD_MANIFESTO.md](AETHELGARD_MANIFESTO.md).*
