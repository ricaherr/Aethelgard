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
- Range Trading completo
- Breakout Trading en transiciones
- Módulos de estrategias independientes

### ✅ Fase 2.3: Score Dinámico y Gestión de Instrumentos (COMPLETADA - Enero 2026)

**Objetivo:** Filtrado inteligente de señales por calidad (score) y gestión granular de instrumentos activos/inactivos por categoría de mercado.

**Implementado (Nivel 1 - Validación con JSON):**

| Componente | Descripción | Estado |
|------------|-------------|--------|
| `config/instruments.json` | Clasificación FOREX (majors/minors/exotics), CRYPTO, STOCKS, FUTURES con min_score, enabled, spread | ✅ Completado |
| `core_brain/instrument_manager.py` | Clasificador de símbolos, validación de habilitación, score mínimo dinámico, auto-clasificación | ✅ Completado |
| `oliver_velez.py` (modificación) | Integración con InstrumentManager, validación de score antes de generar Signal | ✅ Completado |
| `tests/test_instrument_filtering.py` | 20 tests de filtrado por score, habilitación/deshabilitación por categoría | ✅ 20/20 Pasando |

**Funcionalidades:**
- ✅ **Scores Dinámicos por Categoría**: Majors 70, Minors 75, Exotics 90, Crypto Tier1 75, Altcoins 85
- ✅ **Habilitación/Deshabilitación**: Exóticas y altcoins desactivadas por defecto
- ✅ **Auto-Clasificación**: Símbolos desconocidos clasificados automáticamente (USDSGD → FOREX/majors)
- ✅ **Multiplicadores de Riesgo**: Position sizing ajustado por volatilidad (exotics: 0.5x, majors: 1.0x)
- ✅ **Validación Completa**: Rechazo de setups con score insuficiente o instrumento deshabilitado
- ✅ **Testing Robusto**: Cobertura completa de clasificación, validación e integración
- ✅ **Logs Detallados**: Trazabilidad de por qué se rechaza cada setup

**Beneficios:**
- 🎯 **Control de Calidad**: Solo ejecutar setups con score >= umbral dinámico
- 💰 **Gestión de Costos**: Evitar exóticas con spreads prohibitivos (15-30 pips)
- 🔧 **Flexibilidad**: Activar/desactivar categorías vía config sin código
- 🛡️ **Protección**: Risk multipliers reducidos en instrumentos volátiles
- 📊 **SaaS Ready**: Filtrado por membresía (Basic: solo majors, Premium: todo)

### 🚧 Fase 2.4: Migración a Base de Datos (Próxima Prioridad Alta)

**Objetivo:** Migrar configuración de instrumentos de JSON a base de datos SQLite con soporte multi-usuario.

**Arquitectura 3-Tablas con Pivot:**

| Tabla | Propósito | Registros Iniciales |
|-------|-----------|---------------------|
| `instrument_categories` | Categorías globales (FOREX/majors, CRYPTO/tier1, etc.) | ~12 categorías |
| `instruments` | Símbolos individuales con defaults (EURUSD, BTCUSDT, etc.) | ~50 instrumentos |
| `user_instruments` | Configuración por usuario (tabla PIVOT) | 0 (se crea on-demand) |

**Cascading Defaults:**
1. **User Override** → `user_instruments.min_score` (más específico)
2. **Instrument Default** → `instruments.min_score_override`
3. **Category Default** → `instrument_categories.min_score_default`
4. **Global Fallback** → 80.0 (conservador)

**Tareas Pendientes:**

| # | Tarea | Descripción | Prioridad |
|---|-------|-------------|-----------|
| 1 | Script de migración | `scripts/migrate_instruments_to_db.py` para seed data de JSON → DB | 🔴 Alta |
| 2 | Modificar InstrumentManager | Leer de DB con `user_id`, mantener JSON fallback | 🔴 Alta |
| 3 | StorageManager enhancement | `get_user_instrument_config(user_id, symbol)` con cascading | 🔴 Alta |
| 4 | Tests multi-usuario | Validar aislamiento entre usuarios, defaults en cascada | 🟡 Media |
| 5 | Dashboard UI | Tab "Mis Instrumentos" con toggles/sliders por categoría | 🟢 Baja |

**Beneficios de DB sobre JSON:**
- ✅ **Multi-Tenant**: Usuario 1 = conservador, Usuario 2 = agresivo, configs aisladas
- ✅ **Auditoría**: `updated_at` rastrea cambios, posible tabla `audit_log`
- ✅ **UI Editable**: Dashboard puede mostrar/editar configs sin tocar archivos
- ✅ **Escalabilidad**: 10,000 usuarios × 100 instrumentos con índices eficientes
- ✅ **Sin Duplicación**: Un registro EURUSD, múltiples configs en `user_instruments`
- ✅ **Defaults Inteligentes**: Nuevos instrumentos heredan config de categoría

**Pendiente de Implementación (Niveles 2-4 - Score Adaptativo):**
- **Nivel 2: Score Adaptativo**: Eliminar base arbitraria (60), penalizar por spread, pesos ajustados (40/30/30)
- **Nivel 3: Calibración Backtesting**: Ajustar umbrales basados en win-rate histórico (1000+ trades)
- **Nivel 4: Score Predictivo (ML)**: Modelo de machine learning para probabilidad de éxito (500+ trades reales)

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
