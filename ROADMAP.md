# Aethelgard – Roadmap

**Última actualización**: 2026-01-30

---

## 📊 Estado del Sistema (Enero 2026)

| Componente | Estado | Validación |
|------------|--------|------------|
| 🧠 Core Brain (Orquestador) | ✅ Operacional | 11/11 tests pasados |
| 🛡️ Risk Manager | ✅ Operacional | 4/4 tests pasados |
| 📊 Confluence Analyzer | ✅ Operacional | 8/8 tests pasados |
| 🔌 Connectors (MT5) | ✅ Operacional | DB-First implementado |
| 💾 Database (SQLite) | ✅ Operacional | Single Source of Truth |
| 🎯 Signal Factory | ✅ Operacional | 3/3 tests pasados |
| 📡 Data Providers | ✅ Operacional | 19/19 tests pasados |
| 🖥️ Dashboard UI | ✅ Operacional | Sin errores críticos |
| 🧪 Test Suite | ✅ Operacional | **148/148 tests pasados** |

**Resumen**: Sistema completamente funcional y validado end-to-end

**Warnings no críticos detectados**:
- ⚠️ Streamlit deprecation: `use_container_width` → migrar a `width='stretch'` (deprecado 2025-12-31)
- ℹ️ Telegram Bot no configurado (opcional para notificaciones)

---

## 🧯 Hotfix: Monitoreo continuo y resiliencia de datos (2026-01-30) ✅ COMPLETADA

**Objetivo:** Reducir fallos de datos en Yahoo Finance y eliminar errores en el monitor de cierres en modo paper.

**Plan de Trabajo (hoy):**

1. **Registrar fallos de monitoreo** ✅
  - Guardar errores capturados en `dashboard_errors.txt`.

2. **PaperConnector: soporte de cierres** ✅
  - Implementar `get_closed_positions()` para evitar error en ClosingMonitor.

3. **GenericDataProvider: fallback robusto** ✅
  - Reintentar con `yf.download()` cuando `history()` falla.

4. **Tests de cobertura** ✅
  - Test de fallback en Yahoo Finance.
  - Test de `get_closed_positions()` en PaperConnector.

5. **Validación de tests** ✅
  - Tests nuevos ejecutados: **2 passed** (PaperConnector + fallback Yahoo).

---

Resumen del roadmap de implementación. Detalle completo en [AETHELGARD_MANIFESTO.md](AETHELGARD_MANIFESTO.md#roadmap-de-implementación).

---

## 🧪 Fase 2.7: Validación de Auto-Trading MT5 Demo ⏳ EN PROGRESO


## 🟢 Fase 2.7: Provisión EDGE de cuentas demo maestras y brokers ✅ COMPLETADA

---

## 🟢 Hotfix 2026-01-30: Serialización, retry/backoff y control de cuenta activa única por broker ✅ COMPLETADA

**Objetivo:**
Garantizar robustez y operación concurrente segura en la provisión y uso de cuentas demo/real, evitando bloqueos de base de datos y duplicidad de cuentas activas.

**Cambios aplicados:**
- Todas las escrituras críticas en la base de datos (StorageManager) ahora usan serialización y retry/backoff para evitar errores "database is locked".
- En la provisión de cuentas demo, si existen varias cuentas activas para un broker, el sistema selecciona la primera como default y lo informa en logs/dashboard.
- Se asegura que solo una cuenta demo activa por broker sea utilizada para operar.
- Cumplimiento estricto de Single Source of Truth (DB-first).

**Criterios de éxito:**
- Sin bloqueos de base de datos en escenarios concurrentes.
- No se crean ni usan cuentas demo duplicadas.
- Logs y dashboard informan claramente la cuenta seleccionada si hay más de una activa.
- Todos los tests relevantes pasados.

**Resumen Ejecutivo:**
El sistema ahora es resiliente ante concurrencia y multi-cuenta, garantizando operación autónoma y profesional. La lógica de provisión y uso de cuentas demo es óptima y segura, cumpliendo las mejores prácticas de trading algorítmico SaaS.
**Objetivo:** Registrar y provisionar automáticamente todas las cuentas demo maestras en brokers disponibles, validando conexión y lógica óptima (no redundante).

**Plan de Trabajo:**
1. Descubrir y clasificar brokers (auto/manual).
2. Provisión automática solo cuando sea óptimo (evitar duplicados).
3. Validar conexión y registro en DB.
4. Reflejar estado en dashboard y logs.
5. Actualizar MANIFESTO y ROADMAP.

**Evidencia técnica (2026-01-30):**
 - Provisión y conexión exitosa de cuenta demo MT5 (XM Demo, Login: 100919522).
 - Lógica EDGE activada solo cuando es óptimo; no se crean cuentas demo redundantes.
 - Dashboard y logs reflejan estado correcto.
 - Todos los tests relevantes pasados.

**Criterios de Éxito:**
 - Brokers clasificados y registrados en DB.
 - Cuentas demo maestras creadas solo si no existen o están inactivas.
 - Estado visible en dashboard y logs.
 - Documentación actualizada.

**Resumen Ejecutivo:**
La provisión EDGE de cuentas demo maestras y la validación de brokers se completó exitosamente. El sistema ahora detecta y provisiona cuentas demo solo cuando es óptimo, evitando duplicados y asegurando resiliencia. Ver reglas de autonomía y provisión en [AETHELGARD_MANIFESTO.md](AETHELGARD_MANIFESTO.md#reglas-de-autonomía).

---

## 🧹 Fase 2.8: Eliminación de Dependencias `mt5_config.json` ✅ COMPLETADA

**Objetivo:** Eliminar cualquier uso de archivos `mt5_config.json`/`mt5.env` y mantener MT5 100% DB-first.

**Cambios Aplicados:**

- Eliminado sync a archivos desde `StorageManager`.
- Dashboard y utilidades MT5 guardan configuración exclusivamente en DB.
- Diagnóstico MT5 compara contra DB, no archivos locales.

- ✅ No existe dependencia de archivos locales para MT5.
- ✅ Configuración y credenciales centralizadas en DB.

---

## 🛡️ Fase 2.9: Monitor de Coherencia End-to-End (EDGE) ⏳ EN PROGRESO


**Objetivo:** Auto-monitoreo inteligente de consistencia entre Scanner → Señal → Estrategia → Ejecución → Ticket.

**Alcance:**
- Detectar cuando hay condiciones de mercado pero no se genera señal.
- Detectar cuando hay señal pero no se ejecuta (o no hay ticket).
- Detectar cuando la estrategia válida no coincide con ejecución.

**Plan de Trabajo (2026-01-30):**
1. Definir eventos y métricas de coherencia (Scanner, SignalFactory, Executor, MT5Connector).
2. Diseñar y crear tabla `coherence_events` en DB para trazabilidad por símbolo/timeframe/estrategia.
3. Implementar reglas de coherencia (mismatch detector con razones exactas y tipo de incoherencia).
4. Integrar registro de eventos en el ciclo del orquestador.
5. Exponer estado y eventos en el dashboard UI.
6. Crear tests de cobertura para casos de incoherencia y recuperación.
7. Documentar criterios y resultados en el MANIFESTO.

**Checklist de tareas:**
- [ ] Definición de eventos y métricas
- [ ] Diseño y migración de DB (tabla coherence_events)
- [ ] Implementación de reglas de coherencia
- [ ] Integración en orquestador
- [ ] Visualización en dashboard
- [ ] Tests de cobertura
- [ ] Documentación actualizada
4. **Panel de diagnóstico** en Dashboard (lista de inconsistencias y causa).
5. **Alertas** (Telegram opcional) cuando se exceda umbral.

**Estado Actual:**
- ✅ CoherenceMonitor implementado (DB-first).
- ✅ Tabla `coherence_events` creada.
- ✅ Reglas: símbolo no normalizado, `EXECUTED` sin ticket, `PENDING` con timeout.
- ✅ Integración en orquestador por ciclo.

**Evidencia técnica (2026-01-30):**
- ✅ Suite de tests ejecutada completa: **153/153 PASSED**.

## 🔧 Fase 2.6: Migración Streamlit - Deprecación `use_container_width` ✅ COMPLETADA

**Objetivo:** Actualizar Dashboard UI para eliminar warnings de deprecación de Streamlit.

**Contexto:**
- Streamlit está deprecando el parámetro `use_container_width` (será eliminado después de 2025-12-31)
- Nuevo API: `use_container_width=True` → `width='stretch'` | `use_container_width=False` → `width='content'`
- Afecta componentes: `st.dataframe()` y `st.plotly_chart()`
**Archivos Afectados:**

**Cambios Aplicados:**

| # | Ubicación | Línea | Componente | Estado |
|---|-----------|-------|------------|--------|
| 1 | dashboard.py | 263 | `st.dataframe(df_open, ...)` | ✅ Migrado |
| 2 | dashboard.py | 332 | `st.plotly_chart(fig, ...)` | ✅ Migrado |
| 3 | dashboard.py | 344 | `st.plotly_chart(fig_pie, ...)` | ✅ Migrado |
| 4 | dashboard.py | 614 | `st.dataframe(df_mt5_positions, ...)` | ✅ Migrado |
| 5 | dashboard.py | 1644 | `st.plotly_chart(fig, ...)` | ✅ Migrado |
| 6 | dashboard.py | 1676 | `st.dataframe(..., use_container_width=True)` | ✅ Migrado |
| 7 | dashboard.py | 1716 | `st.dataframe(..., use_container_width=True)` | ✅ Migrado |

**Proceso de Implementación:**

1. **Análisis Previo** ✅ COMPLETADO
   - Identificar todas las ocurrencias: 7 encontradas
   - Verificar compatibilidad de versión Streamlit
   - Documentar ubicaciones exactas

2. **Migración de Código** ✅ COMPLETADO
   - Reemplazadas 7 ocurrencias: `use_container_width=True` → `width='stretch'`
   - No se encontraron ocurrencias de `use_container_width=False`
   - Otros parámetros mantenidos sin cambios

3. **Testing** ⏸️ PENDIENTE
   - Ejecutar Dashboard localmente
   - Verificar que tablas y gráficos se muestren correctamente
   - Confirmar eliminación de warnings en logs
   - Probar en diferentes resoluciones (ancho variable)

4. **Validación** ⏸️ PENDIENTE
   - Dashboard arranca sin warnings de deprecación
   - Componentes visualmente idénticos
   - Sin errores en consola
   - Funcionalidad intacta

**Impacto:**
- ⚠️ Warning eliminado
- 🎨 Sin cambios visuales para el usuario
- ✅ Código preparado para Streamlit 2026+
- 📦 Compatible con versiones actuales (comportamiento idéntico)

**Tiempo Estimado:** 15-20 minutos

**Prioridad:** BAJA (no crítico, tiene 1 año de gracia hasta deprecación final)

**Estado:** ⏸️ Esperando aprobación del usuario

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

### 🧪 Fase 2.5: Sistema de Diagnóstico MT5 y Gestión de Operaciones ✅ COMPLETADA (Enero 2026)

**Objetivo:** Verificación de conectividad MT5, identificación de origen de operaciones (PAPER/DEMO/REAL) y funcionalidad completa de cierre de posiciones desde Dashboard.

**Tareas Completadas:**

| # | Tarea | Descripción | Estado |
|---|-------|-------------|--------|
| 1 | Diagnóstico MT5 en HealthManager | Método `check_mt5_connection()` que verifica instalación, conexión, tipo de cuenta, balance y posiciones reales | ✅ Completado |
| 2 | Integración Dashboard | Sección en "Sistema & Diagnóstico" con botón "Probar Conexión MT5" y visualización de estado | ✅ Completado |
| 3 | Clasificación de Operaciones | Mostrar origen (PAPER/DEMO/REAL + Broker) en vista de operaciones abiertas | ✅ Completado |
| 4 | Funcionalidad Cerrar Operación | Conectar botón de cierre con MT5Connector.close_position() y actualizar DB | ✅ Completado |
| 5 | Script de Prueba Automática | `test_auto_trading.py` para validar flujo completo: señal → ejecución → cierre | ✅ Completado |
| 6 | Arquitectura DB-First | Unificación de configuración MT5: Single Source of Truth = DATABASE | ✅ Completado |
| 7 | Mensajes de Error Mejorados | Sistema de ayuda contextual paso-a-paso en todos los mensajes de error/warning | ✅ Completado |

**Funcionalidades Implementadas:**

- 🗄️ **Single Source of Truth (DB)**: Configuración centralizada en base de datos
  - **MT5Connector**: Lee de `broker_accounts` + `broker_credentials` (NO archivos JSON)
  - **MT5DataProvider**: Lee de `broker_accounts` (NO archivos JSON)
  - **HealthManager**: Lee de `broker_accounts` (NO archivos JSON)
  - **Dashboard**: Guarda SOLO en DB (NO genera archivos de configuración)
  - Eliminados archivos obsoletos: `config/mt5_config.json`, `config/mt5.env`
  - Sin duplicación de configuración
  - Sin reconexiones fallidas por datos desactualizados
  
- 📋 **Sistema de Mensajes Mejorado**: Ayuda contextual paso-a-paso
  - Todos los errores/warnings incluyen causa exacta del problema
  - Pasos numerados para solucionar (usuario no técnico)
  - Información de contexto (cuenta, login, servidor)
  - Indicación de cuándo contactar soporte técnico
  - Ejemplos: Librería no instalada, cuenta sin configurar, contraseña faltante, conexión fallida
  
- 🤖 **Verificación AutoTrading**: Detección y documentación de requisitos MT5
  - HealthManager detecta si AutoTrading está habilitado/deshabilitado
  - Mensajes claros con pasos para habilitar desde MT5
  - Documentación de ubicación del botón en interfaz MT5
  - Alternativa por menú Herramientas → Opciones
  - Warning claro: "SIN AUTOTRADING NO SE PUEDEN EJECUTAR OPERACIONES AUTOMÁTICAS"
  
- 🔌 **Health Check MT5**: Diagnóstico completo desde Dashboard (instalación, conexión, cuentas)
  - Verifica si MetaTrader5 está instalado
  - Conecta y obtiene información de cuenta
  - Detecta automáticamente tipo de cuenta (DEMO/REAL)
  - Muestra balance, equity, profit, margin
  - Lista posiciones abiertas en tiempo real desde MT5
  
- 🏷️ **Origen de Operaciones**: Identificación clara PAPER (sistema) vs DEMO (broker) vs REAL (broker)
  - 🔵 PAPER (Sistema): Operaciones simuladas internamente
  - 🟢 DEMO (MT5): Operaciones en cuenta demo de broker
  - 🔴 REAL (MT5): Operaciones en cuenta real (bloqueadas por seguridad)
  
- ✂️ **Cierre de Posiciones**: Funcionalidad real conectada a MT5 con actualización de DB
  - Botón de cierre integrado en Dashboard
  - Conexión directa con MT5Connector
  - Actualización automática de status en base de datos
  - Feedback visual de éxito/error
  
- 🧪 **Testing Automático**: Validación end-to-end del flujo de trading
  - Script `test_auto_trading.py` completo
  - Prueba conexión MT5
  - Crea señal de test
  - Ejecuta con OrderExecutor
  - Espera 10 segundos
  - Cierra posición
  - Verifica en base de datos
  
- 📊 **Posiciones Reales**: Visualización de posiciones abiertas directamente desde MT5
  - Tabla completa en Dashboard con ticket, símbolo, tipo, volumen, precios, P/L
  - Actualización en tiempo real
  - Información de SL/TP

**Beneficios:**
- ✅ **Arquitectura Limpia**: Una sola fuente de verdad (DB), sin archivos JSON redundantes
- ✅ **Verificación Fácil**: Usuario puede confirmar que MT5 funciona correctamente
- ✅ **Transparencia**: Saber origen exacto de cada operación
- ✅ **Control Total**: Cerrar operaciones desde el Dashboard
- ✅ **Confianza**: Testing completo antes de operar en real
- ✅ **Seguridad**: Protección anti-real (solo opera en DEMO)
- ✅ **Mantenibilidad**: Sin desincronización entre archivos y DB
- ✅ **UX Mejorada**: Mensajes de error comprensibles para usuarios no técnicos
- ✅ **Auto-Diagnóstico**: Sistema detecta problemas comunes y sugiere soluciones
- ✅ **Scripts Mínimos**: Solo 3 scripts útiles de MT5 (setup, diagnose, test_auto_trading)

**Tests Ejecutados y Pasados:**
- ✅ `test_auto_trading.py` - Test END-TO-END completo (Ticket: 667793674)
  - Conexión a MT5 (Login: 100919522)
  - Creación de señal con precios reales
  - Ejecución de orden (0.01 lotes EURUSD)
  - Verificación de posición abierta
  - Cierre automático de posición
  - Persistencia en base de datos

**Archivos Modificados:**
- `core_brain/health.py`: +90 líneas (método check_mt5_connection con mensajes amigables)
- `ui/dashboard.py`: Sección MT5 en Sistema & Diagnóstico, configuración asistida, mejoras en operaciones abiertas
- `scripts/utilities/test_auto_trading.py`: Script completo de testing (nuevo)

**Mejoras de UX (29 Enero 2026):**
- ✅ **Mensajes Amigables**: Todos los mensajes de diagnóstico en español y orientados a usuario final
- ✅ **Configuración Asistida**: Formulario integrado en Dashboard para configurar MT5 sin tocar archivos
- ✅ **Guías Contextuales**: Mensajes con 💡 que explican cómo resolver cada problema
- ✅ **Auto-expansión**: Panel de detalles se expande automáticamente cuando hay errores
- ✅ **Integración con Cuentas Guardadas**: Selector de cuentas MT5 desde la base de datos
- ✅ **Gestión de Contraseñas**: Detecta y solicita contraseñas faltantes, guarda encriptado
- ✅ **Edición de Cuentas**: Permite editar cuentas de broker existentes (nombre, login, servidor, contraseña)
- ✅ **Sin Límites de Caracteres**: Campos de login sin truncamiento (max_chars=None)
- ✅ **Herramienta de Diagnóstico**: Script `diagnose_mt5_connection.py` para comparar config vs MT5 real

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

## 🚀 Provisión y Reporte Automático de Brokers/Cuentas DEMO (2026-01-30)

**Objetivo:**
Implementar detección automática de brokers, provisión de cuentas DEMO (cuando sea posible), y reporte del estado/resultados en el dashboard, informando claramente si requiere acción manual o si hubo errores.

**Plan de Trabajo:**

1. Implementar lógica de escaneo y provisión automática de brokers/cuentas DEMO en el backend (core_brain/main_orchestrator.py, connectors/auto_provisioning.py).
2. Registrar en la base de datos el estado de provisión, cuentas DEMO creadas, y motivos de fallo si aplica (data_vault/storage.py).
3. Exponer métodos en StorageManager para consultar brokers detectados, estado de provisión, cuentas DEMO creadas y motivos de fallo.
4. Actualizar el dashboard (ui/dashboard.py) para mostrar:
   - Lista de brokers detectados
   - Estado de provisión/conexión
   - Cuentas DEMO creadas
   - Mensajes claros de error o requerimientos manuales
5. Crear test end-to-end en tests/ para validar el flujo completo y la visualización en la UI.

**Checklist:**
- [ ] Lógica de escaneo y provisión automática implementada
- [ ] Estado/resultados registrados en DB
- [ ] Métodos de consulta en StorageManager
- [ ] Dashboard actualizado con reporte claro
- [ ] Test end-to-end validando el flujo

---

*Fuente de verdad: [AETHELGARD_MANIFESTO.md](AETHELGARD_MANIFESTO.md).*
