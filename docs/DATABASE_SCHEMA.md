# Aethelgard Database Schema v3.2 (ARCH-SSOT-2026-010)

## Overview

**Database Engine**: SQLite 3 (Idempotent, Multi-Tenant Capable)
**Architecture**: Unified Global DB + Tenant Templates
**Current Status**: Single Admin in Global DB (No Active Tenants)
**Initialization**: Pure DDL via `data_vault/schema.py` + Migrations
**Source of Truth**: This document + Global DB (`data_vault/global/aethelgard.db`)
**Last Updated**: 2026-03-25 (Deuda documental — sincronización total con DB real)

⚠️ **CONTRATO ARQUITECTÓNICO FINAL**: Esta estructura es vinculante. La DB global es la ÚNICA FUENTE DE VERDAD en operación.

---

## 🗂️ ARQUITECTURA ACTUAL (Real)

| DB | Contenido | Propósito | Tablas |
|----|-----------|----------|--------|
| **data_vault/global/aethelgard.db** | sys_* + usr_* + legacy | ADMIN principal (datos globales + personales) | **46 tablas** |
| **data_vault/templates/usr_template.db** | usr_* | Plantilla para clonar nuevos tenants | 16 tablas |
| **data_vault/tenants/{uuid}/** | (vacío) | Cuando se cree un nuevo usuario, se clonará template aquí | — |

---

## ✅ CAPA GLOBAL: ADMIN DATABASE (`data_vault/global/aethelgard.db`)

### Contenido Real (25-Mar-2026) — 46 tablas

**TABLAS SYS_* (Compartidas — Global)**: 26 tablas

```
sys_audit_logs                   - Auditoría de acciones y transiciones de modo (SYSTEM user)
sys_broker_accounts              - Configuración de cuentas de broker
sys_brokers                      - Metadatos de brokers registrados
sys_config                       - Configuración del sistema (SSOT)
sys_consensus_events             - Eventos de consenso multi-estrategia
sys_cooldown_tracker             - Control de cooldown de señales por estrategia/par
sys_credentials                  - Credenciales encriptadas de broker accounts
sys_data_providers               - Proveedores de datos (DB-driven, connector_module/class)
sys_dedup_events                 - Log de señales deduplicadas por DedupLearner
sys_dedup_rules                  - Reglas de ventana de dedup por (symbol, timeframe, strategy)
sys_economic_calendar            - Calendario económico global (NFP, BCE, etc.)
sys_execution_feedback           - Feedback de ejecución — rejection logger NIVEL0
sys_market_pulse                 - Estado del mercado (global scanner, JSON blob)
sys_platforms                    - Plataformas de trading (MT5, cTrader, etc.)
sys_regime_configs               - Pesos de métricas por régimen de mercado
sys_shadow_instances             - Instancias activas en modo SHADOW (lifecycle)
sys_shadow_performance_history   - Historial de evaluación de instancias SHADOW (3 Pilares)
sys_shadow_promotion_log         - Log de promociones SHADOW → LIVE
sys_signal_pipeline              - Auditoría de etapas de señales (sys scope) [legacy DDL]
sys_signal_quality_assessments   - Evaluaciones de calidad de señales (SignalQualityScorer)
sys_signal_ranking               - Ranking global de estrategias (formerly usr_performance)
sys_signals                      - Señales generadas globales
sys_strategies                   - Registro de estrategias — lifecycle BACKTEST→SHADOW→LIVE
sys_strategy_logs                - Logs de rendimiento de estrategias por activo [legacy DDL]
sys_symbol_mappings              - Mapeo de símbolos internos ↔ proveedor
sys_users                        - Usuarios del sistema (auth unificada)
```

**TABLAS USR_* (Personales del ADMIN)**: 16 tablas

```
usr_anomaly_events               - Eventos de anomalías detectadas (Z-Score, Flash Crash)
usr_assets_cfg                   - Activos que el ADMIN opera (SSOT de instrumentos habilitados)
usr_broker_accounts              - Cuentas de broker del usuario ADMIN
usr_coherence_events             - Eventos de incoherencia detectados en señales
usr_connector_settings           - Toggle manual de conectores (enabled/disabled)
usr_edge_learning                - Aprendizaje EDGE por detección/acción/resultado
usr_execution_logs               - Logs de ejecución de órdenes con slippage y latencia
usr_notification_settings        - Configuración de proveedores de notificación
usr_notifications                - Notificaciones del sistema (versión tenant)
usr_performance                  - ⚠️ DEPRECATED — usar sys_signal_ranking
usr_position_history             - Historial de modificaciones a posiciones (SL/TP events)
usr_preferences                  - Preferencias de la UI y trading del ADMIN
usr_signal_pipeline              - Auditoría de etapas de señales (usr scope)
usr_strategy_logs                - Logs de rendimiento de estrategias (usr scope)
usr_trades                       - Ejecuciones/trades del ADMIN
usr_tuning_adjustments           - Ajustes de tuning del sistema (EdgeTuner)
```

**TABLAS INFRAESTRUCTURA / LEGACY**: 4 tablas

```
edge_learning        - Tabla de aprendizaje EDGE (legacy — distinta de usr_edge_learning)
notifications        - Notificaciones (legacy — distinta de usr_notifications)
position_metadata    - Metadatos de posiciones abiertas (NIVEL0 SSOT — monitoreo)
session_tokens       - Tokens de sesión (auth — NIVEL0 SSOT)
```

> ⚠️ **Nota sobre tablas Infra/Legacy**: `edge_learning` y `notifications` son tablas anteriores a la convención `sys_/usr_*` — su DDL no está en `schema.py`. `position_metadata` y `session_tokens` fueron movidas a `schema.py` en v2.x (NIVEL0).

> ⚠️ **Tablas en DB pero NO en `schema.py`**: `edge_learning`, `notifications`, `sys_signal_pipeline`, `sys_strategy_logs`, `usr_performance` — sus DDLs existen en la DB pero no en el archivo de inicialización. Migración pendiente en deuda técnica.

---

## 📋 DETALLE DE TABLAS

### `sys_config` (Global Configuration SSOT)

**Scope**: Clave-valor para toda la configuración del sistema.
**Governance**: System R/W; Admin R/W.

| Column | Type | Purpose |
|--------|------|---------|
| key | TEXT PK | Clave de configuración |
| value | TEXT | Valor (JSON o string) |
| updated_at | TIMESTAMP | Última modificación |

**Claves relevantes**: `account_balance`, `aso_autonomy_level`, `tenant_template_bootstrap_mode`, `tenant_template_bootstrap_done`

---

### `sys_users` (Authentication — unified)

**Scope**: Usuarios del sistema (reemplaza `sys_auth` de v1.x).
**Governance**: Admin escribe; System lee.

| Column | Type | Purpose |
|--------|------|---------|
| id | TEXT PK | UUID de usuario |
| email | TEXT UNIQUE | Email de acceso |
| password_hash | TEXT | Hash bcrypt |
| role | TEXT | `admin` \| `trader` |
| status | TEXT | `active` \| `suspended` \| `deleted` |
| tier | TEXT | `BASIC` \| `PREMIUM` \| `INSTITUTIONAL` |
| created_at | TIMESTAMP | Fecha de alta |
| updated_at | TIMESTAMP | Última modificación |
| deleted_at | TIMESTAMP | Soft-delete |
| created_by / updated_by | TEXT | Trazabilidad de gestión |

---

### `sys_strategies` (Strategy Registry — Lifecycle + Backtesting)

**Scope**: Registro global de todas las estrategias. Controla el pipeline BACKTEST → SHADOW → LIVE.
**Governance**: Admin/System escribe; todos los componentes leen.
**Migration**: Idempotente — `run_migrations()` en `data_vault/schema.py` agrega columnas con `ALTER TABLE`.

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| class_id | TEXT PK | — | Identificador único (e.g. `MOM_BIAS_0001`) |
| mnemonic | TEXT | — | Nombre corto legible |
| version | TEXT | `1.0` | Versión semántica |
| description | TEXT | — | Descripción de la estrategia |
| type | TEXT | — | Tipo (PYTHON_CLASS, etc.) |
| class_file | TEXT | — | Módulo Python |
| class_name | TEXT | — | Clase Python |
| required_sensors | TEXT | `[]` | JSON: IDs de sensores requeridos |
| logic | TEXT | NULL | Descripción de lógica |
| affinity_scores | TEXT | `{}` | JSON: evidencia empírica de rendimiento (darwin ranking) |
| market_whitelist | TEXT | `[]` | JSON: activos permitidos |
| readiness | TEXT | `UNKNOWN` | Nivel de preparación |
| readiness_notes | TEXT | NULL | Notas de preparación |
| mode | TEXT | `BACKTEST` | `BACKTEST` \| `SHADOW` \| `LIVE` \| `DISABLED` |
| score_backtest | REAL | `0.0` | Score del ScenarioBacktester |
| score_shadow | REAL | `0.0` | Score de evaluación SHADOW (3 Pilares) |
| score_live | REAL | `0.0` | Score de trading real |
| score | REAL | `0.0` | Score consolidado: `live×0.50 + shadow×0.30 + backtest×0.20` |
| last_backtest_at | TIMESTAMP | NULL | Último backtest completado (referencia de cooldown) |
| **required_regime** | TEXT | `ANY` | ⭐ **HU 7.8** — Filtro de régimen: `TREND` \| `RANGE` \| `VOLATILE` \| `ANY` |
| **required_timeframes** | TEXT | `[]` | ⭐ **HU 7.8** — JSON: timeframes requeridos (e.g. `["M5","M15"]`). Vacío = descubrimiento empírico |
| **execution_params** | TEXT | `{}` | ⭐ **HU 7.8** — JSON: `confidence_threshold`, `risk_reward` |
| created_at | TIMESTAMP | NOW | Registro inicial |
| updated_at | TIMESTAMP | NOW | Última modificación |

> ⭐ **Sprint 9 (HU 7.8)** — `required_regime`, `required_timeframes`, `execution_params` agregados 2026-03-24 vía migración idempotente.

**Score Formula**: `score = score_live × 0.50 + score_shadow × 0.30 + score_backtest × 0.20`

**Lifecycle**: `BACKTEST ──(score ≥ 0.75)──→ SHADOW ──(3 Pilares pass)──→ LIVE`

---

### `sys_audit_logs` (Operational Audit Trail)

**Scope**: Auditoría de acciones de sistema y transiciones de modo operacional.
**Governance**: System/Admin escribe (append-only); Admin lee.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| user_id | TEXT NOT NULL | `SYSTEM` para eventos autónomos, UUID para acciones de usuario |
| action | TEXT | Tipo de evento (`MODE_TRANSITION`, `STRATEGY_PROMOTED`, etc.) |
| resource | TEXT | Componente origen (`OperationalModeManager`, etc.) |
| resource_id | TEXT | ID del recurso afectado (opcional) |
| old_value | TEXT | Estado anterior |
| new_value | TEXT | Estado nuevo |
| status | TEXT | `success` \| `error` |
| reason | TEXT | Razón del evento |
| timestamp | TIMESTAMP | ISO8601 UTC |
| trace_id | TEXT UNIQUE | ID de trazabilidad |

> ⭐ **Sprint 9 (HU 10.7)** — `OperationalModeManager` escribe `MODE_TRANSITION` cuando cambia el contexto operacional.

---

### `sys_market_pulse` (Global Market Cache)

**Scope**: Snapshot de mercado por símbolo (blob JSON). Global Scanner escribe; todos leen.
**Governance**: Scanner escribe; tenants leen.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| symbol | TEXT | Instrumento financiero |
| timestamp | TIMESTAMP | Timestamp del snapshot |
| data | TEXT | JSON blob con OHLCV, indicadores, régimen |

---

### `sys_economic_calendar` (Global Economic Events)

**Scope**: Eventos económicos globales (NFP, BCE, etc.). NewsSanitizer inserta; tenants leen.

| Column | Type | Purpose |
|--------|------|---------|
| event_id | TEXT PK | ID único del evento |
| event_name | TEXT | Nombre del evento |
| country | TEXT | País (ISO 3166-1 alpha-2) |
| currency | TEXT | Moneda afectada (ISO 4217) |
| impact_score | INTEGER | Nivel de impacto numérico |
| event_time_utc | TIMESTAMP | Hora del evento UTC |
| forecast | REAL | Valor esperado |
| previous | REAL | Valor anterior |
| actual | REAL | Valor real (NULL hasta publicarse) |
| source | TEXT | Origen (`economic_data_gateway`) |
| created_at / updated_at | TIMESTAMP | Trazabilidad |

---

### `sys_signals` (Global Signals)

**Scope**: Señales generadas globalmente por el motor de estrategias.

| Column | Type | Purpose |
|--------|------|---------|
| id | TEXT | ID de señal |
| symbol | TEXT | Instrumento |
| signal_type | TEXT | Tipo de señal |
| confidence | REAL | Fuerza de la señal (0–1) |
| timestamp | NUM | Timestamp de generación |
| metadata | TEXT | JSON con contexto adicional |
| connector_type | TEXT | Conector de origen |
| timeframe | TEXT | Marco temporal |
| price | REAL | Precio de referencia |
| direction | TEXT | `BUY` \| `SELL` |
| status | TEXT | `PENDING` \| `EXECUTED` \| `REJECTED` \| `EXPIRED` |
| created_at / updated_at | NUM | Trazabilidad |
| origin_mode | TEXT | Modo de origen (`BACKTEST`, `SHADOW`, `LIVE`) |
| strategy_id | TEXT | Estrategia que generó la señal |
| score | REAL | Score de calidad |
| source | TEXT | Fuente de la señal |

---

### `sys_signal_ranking` (Strategy Performance Registry)

**Scope**: Ranking global de estrategias por rendimiento. Reemplaza `usr_performance` (deprecated).
**Governance**: Sistema escribe; todos leen.

| Column | Type | Purpose |
|--------|------|---------|
| strategy_id | TEXT PK | ID de la estrategia |
| profit_factor | REAL | Factor de ganancia |
| win_rate | REAL | Tasa de acierto |
| drawdown_max | REAL | Drawdown máximo |
| sharpe_ratio | REAL | Ratio Sharpe |
| consecutive_losses | INTEGER | Rachas de pérdidas |
| execution_mode | TEXT | Modo activo (`SHADOW`, `LIVE`) |
| trace_id | TEXT UNIQUE | ID de trazabilidad |
| total_trades / completed_last_50 / total_usr_trades | INTEGER | Contadores |
| last_update_utc | TIMESTAMP | Última actualización |
| created_at / updated_at | TIMESTAMP | Trazabilidad |

---

### `sys_shadow_instances` (SHADOW Lifecycle)

**Scope**: Instancias de estrategias en evaluación SHADOW. Controla el ciclo de vida INCUBATING → SHADOW_READY → PROMOTED_TO_REAL.

| Column | Type | Purpose |
|--------|------|---------|
| instance_id | TEXT PK | UUID de instancia |
| strategy_id | TEXT | Estrategia evaluada |
| account_id | TEXT | Cuenta de broker |
| account_type | TEXT | `DEMO` \| `REAL` |
| parameter_overrides | TEXT | JSON con overrides de parámetros |
| regime_filters | TEXT | JSON con filtros de régimen |
| birth_timestamp | TIMESTAMP | Cuando nació la instancia |
| status | TEXT | `INCUBATING` \| `SHADOW_READY` \| `PROMOTED_TO_REAL` \| `DEAD` \| `QUARANTINED` |
| total_trades_executed | INTEGER | Trades ejecutados |
| profit_factor / win_rate / max_drawdown_pct | REAL | Métricas de evaluación |
| consecutive_losses_max / equity_curve_cv | INTEGER/REAL | Métricas 3 Pilares |
| promotion_trace_id / backtest_trace_id | TEXT | Trazabilidad |
| target_regime | TEXT | Régimen objetivo |
| backtest_score | REAL | Score de backtest previo |
| created_at / updated_at | TIMESTAMP | Trazabilidad |

---

### `sys_shadow_performance_history` (SHADOW Evaluation Log)

**Scope**: Historial de evaluaciones de 3 Pilares de instancias SHADOW.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| instance_id | TEXT | FK → sys_shadow_instances |
| evaluation_date | DATE | Fecha de evaluación |
| pillar1_status / pillar2_status / pillar3_status | TEXT | `PASS` \| `FAIL` \| `UNKNOWN` |
| overall_health | TEXT | `HEALTHY` \| `DEAD` \| `QUARANTINED` \| `MONITOR` \| `INCUBATING` |
| event_trace_id | TEXT | Trazabilidad |
| created_at | TIMESTAMP | Registro |

---

### `sys_shadow_promotion_log` (SHADOW → LIVE Promotions)

**Scope**: Log de aprobaciones y rechazos de promoción SHADOW → LIVE.

| Column | Type | Purpose |
|--------|------|---------|
| promotion_id | INTEGER PK | Auto-increment |
| instance_id | TEXT | FK → sys_shadow_instances |
| trace_id | TEXT UNIQUE | ID de trazabilidad |
| promotion_status | TEXT | `PENDING` \| `APPROVED` \| `REJECTED` \| `EXECUTED` |
| pillar1_passed / pillar2_passed / pillar3_passed | BOOLEAN | Resultados de pilares |
| approval_timestamp / execution_timestamp | TIMESTAMP | Tiempos de proceso |
| notes | TEXT | Observaciones |
| created_at | TIMESTAMP | Registro |

---

### `sys_dedup_rules` (Deduplication Configuration)

**Scope**: Reglas de ventana de deduplicación por (symbol, timeframe, strategy). DedupLearner ajusta automáticamente.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| symbol / timeframe / strategy | TEXT | Clave compuesta UNIQUE |
| base_window_minutes / current_window_minutes | INTEGER | Ventanas base y adaptativa |
| volatility_factor / regime_factor | REAL | Factores de ajuste |
| last_adjusted | TIMESTAMP | Último ajuste automático |
| data_points_observed | INTEGER | Señales observadas para aprendizaje |
| learning_enabled | BOOLEAN | Si DedupLearner puede ajustar |
| manual_override / override_comment | BOOLEAN/TEXT | Override manual |
| trace_id | TEXT | Trazabilidad |
| created_at / updated_at | TIMESTAMP | Trazabilidad |

---

### `sys_dedup_events` (Deduplication Log)

**Scope**: Log de cada señal deduplicada (por qué fue filtrada y gap medido).

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| symbol / timeframe / strategy | TEXT | Contexto de la señal |
| signal_id / previous_signal_id | TEXT | Señal filtrada y señal previa |
| gap_minutes | REAL | Gap en minutos entre señales |
| dedup_reason | TEXT | Motivo del filtro |
| created_at | TIMESTAMP | Registro |

---

### `sys_cooldown_tracker` (Signal Cooldown Registry)

**Scope**: Señales en cooldown tras fallo de ejecución. Controla retries.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| signal_id | TEXT UNIQUE | Señal en cooldown |
| symbol / strategy | TEXT | Contexto |
| failure_reason | TEXT | Razón del fallo |
| failure_time | TIMESTAMP | Cuándo falló |
| retry_count | INTEGER | Intentos acumulados |
| cooldown_minutes | INTEGER | Duración del cooldown |
| cooldown_expires | TIMESTAMP | Cuándo expira el cooldown |
| volatility_zscore | REAL | Z-Score de volatilidad en el momento |
| regime | TEXT | Régimen en el momento del fallo |
| trace_id | TEXT | Trazabilidad |
| created_at / updated_at | TIMESTAMP | Trazabilidad |

---

### `sys_consensus_events` (Multi-Strategy Consensus)

**Scope**: Eventos donde múltiples estrategias coinciden en dirección/símbolo.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| symbol | TEXT | Instrumento |
| direction | TEXT | `BUY` \| `SELL` |
| consensus_strength | REAL | Fuerza del consenso |
| num_strategies | INTEGER | Número de estrategias en consenso |
| bonus | REAL | Bonus de score aplicado |
| participating_strategies | TEXT | JSON: lista de estrategias |
| confidence | REAL | Confianza calculada |
| trace_id | TEXT | Trazabilidad |
| created_at | TIMESTAMP | Registro |

---

### `sys_execution_feedback` (Execution Rejection Log)

**Scope**: Fallos y rechazos de ejecución de órdenes. Alimenta `CircuitBreaker` y `EdgeTuner`.

| Column | Type | Purpose |
|--------|------|---------|
| feedback_id | TEXT PK | UUID del evento |
| signal_id | TEXT | Señal asociada |
| symbol | TEXT | Instrumento |
| strategy | TEXT | Estrategia asociada |
| reason | TEXT | Motivo del fallo |
| timestamp | TEXT | ISO8601 UTC |
| details | TEXT | JSON con contexto |
| created_at | TIMESTAMP | Registro |

---

### `sys_signal_quality_assessments` (Signal Quality Scores)

**Scope**: Evaluaciones de calidad de señales por `SignalQualityScorer`.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| signal_id | TEXT UNIQUE | FK → sys_signals |
| symbol / timeframe | TEXT | Contexto |
| grade | TEXT | `A+` \| `A` \| `B` \| `C` \| `F` |
| overall_score | REAL | Score total |
| technical_score / contextual_score | REAL | Scores por dimensión |
| consensus_bonus / failure_penalty | REAL | Ajustes |
| metadata | TEXT | JSON adicional |
| trace_id | TEXT | Trazabilidad |
| created_at | TIMESTAMP | Registro |

---

### `sys_regime_configs` (Regime Metric Weights)

**Scope**: Pesos de métricas por régimen de mercado (TREND/RANGE/VOLATILE/SHOCK).

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| regime | TEXT | Régimen (`TREND`, `RANGE`, `VOLATILE`, `SHOCK`) |
| metric_name | TEXT | Nombre de la métrica |
| weight | TEXT | Peso (JSON o REAL) |
| tenant_id | TEXT | NULL = global |
| created_at / updated_at | TIMESTAMP | Trazabilidad |
| UNIQUE(regime, metric_name) | — | Una configuración por par |

---

### `sys_brokers` / `sys_platforms` / `sys_broker_accounts` / `sys_credentials` (Broker Infrastructure)

**Scope**: Catálogo de brokers, plataformas, cuentas y credenciales encriptadas.

| Tabla | Clave | Propósito |
|-------|-------|-----------|
| `sys_brokers` | `id` TEXT PK | Broker registrado con `platform_id` y `config` JSON |
| `sys_platforms` | `id` TEXT PK | Plataforma de trading (`type`, `config`) |
| `sys_broker_accounts` | `account_id` TEXT PK | Cuenta de broker con `supports_data`, `supports_exec`, `balance` |
| `sys_credentials` | `id` TEXT PK | Credenciales encriptadas, FK → `sys_broker_accounts` |

---

### `sys_data_providers` (Data Provider Registry)

**Scope**: Proveedores de datos OHLC — DB-driven, reemplaza configuración hardcoded.

| Column | Type | Purpose |
|--------|------|---------|
| name | TEXT PK | Nombre del proveedor |
| type | TEXT | Tipo de proveedor |
| enabled | BOOLEAN | Activo/inactivo |
| supports_data / supports_exec | BOOLEAN | Capacidades |
| priority | INTEGER | Orden en fallback chain |
| requires_auth | BOOLEAN | Requiere autenticación |
| api_key / api_secret | TEXT | Credenciales (si aplica) |
| connector_module / connector_class | TEXT | Módulo Python para instanciar |
| config / additional_config | TEXT | JSON de configuración |

---

### `sys_symbol_mappings` (Symbol Translation)

**Scope**: Mapeo de símbolos internos ↔ símbolo del proveedor.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| internal_symbol | TEXT | Símbolo interno (ej. `EURUSD`) |
| provider_id | TEXT | ID del proveedor de datos |
| provider_symbol | TEXT | Símbolo en el proveedor (ej. `EUR/USD`) |
| is_default | INTEGER | 1 si es el proveedor default para este símbolo |
| UNIQUE(internal_symbol, provider_id) | — | Sin duplicados |

---

### `usr_assets_cfg` (Asset Configuration — ADMIN)

**Scope**: Activos habilitados para el ADMIN. SSOT de instrumentos que el sistema puede operar.
**Governance**: Admin R/W; Sistema R.

| Column | Type | Purpose |
|--------|------|---------|
| symbol | TEXT PK | Símbolo del activo (ej. `EURUSD`) |
| asset_class | TEXT | `FOREX` \| `CRYPTO` \| `EQUITY` \| `FUTURES` \| `COMMODITY` |
| tick_size | REAL | Tamaño mínimo de movimiento de precio |
| lot_step | REAL | Paso mínimo de lote |
| contract_size | REAL | Tamaño del contrato |
| currency | TEXT | Moneda de cotización (ISO 4217) |
| golden_hour_start / golden_hour_end | TEXT | Ventana de trading óptima (HH:MM) |
| created_at / updated_at | TIMESTAMP | Trazabilidad |

---

### `usr_trades` (Trade History — ADMIN)

**Scope**: Historial de trades ejecutados por el ADMIN.
**Governance**: Append-only post-cierre; trazabilidad 100%.

| Column | Type | Purpose |
|--------|------|---------|
| id | TEXT PK | UUID del trade |
| signal_id | TEXT | Señal que originó el trade |
| symbol | TEXT | Instrumento |
| entry_price / exit_price | REAL | Precios de entrada y salida |
| profit | REAL | P&L en cuenta de cotización |
| exit_reason | TEXT | Motivo de cierre (SL, TP, manual) |
| close_time | TIMESTAMP | Hora de cierre |
| execution_mode | TEXT | `LIVE` \| `SHADOW` \| `BACKTEST` |
| provider | TEXT | Broker (`MT5`, `cTrader`, etc.) |
| account_type | TEXT | `REAL` \| `DEMO` |
| order_id | TEXT | ID de orden en el broker |
| created_at | TIMESTAMP | Registro |

---

### `usr_execution_logs` (Order Execution Detail)

**Scope**: Log detallado de cada ejecución de orden con slippage y latencia.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| signal_id | TEXT | FK → sys_signals |
| symbol | TEXT | Instrumento |
| theoretical_price / real_price | REAL | Precio esperado vs real |
| slippage_pips | REAL | Slippage en pips |
| latency_ms | REAL | Latencia de ejecución en ms |
| status | TEXT | Estado de la ejecución |
| user_id | TEXT | Usuario que ejecutó |
| trace_id | TEXT | Trazabilidad |
| metadata | TEXT | JSON adicional |
| timestamp | TIMESTAMP | Hora de ejecución |

---

### `usr_position_history` (Position Modification Log)

**Scope**: Log de cada modificación a SL/TP de posiciones abiertas (EdgeTuner events).

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| ticket | INTEGER | ID de la posición en el broker |
| symbol | TEXT | Instrumento |
| event_type | TEXT | Tipo de evento (SL_ADJUSTED, TP_ADJUSTED, etc.) |
| timestamp | TIMESTAMP | Cuándo ocurrió |
| old_sl / new_sl | REAL | SL anterior y nuevo |
| old_tp / new_tp | REAL | TP anterior y nuevo |
| reason | TEXT | Motivo del ajuste |
| success | BOOLEAN | Si la modificación fue exitosa |
| error_message | TEXT | Error si falló |
| metadata | TEXT | JSON adicional |

---

### `position_metadata` (Open Positions Snapshot — NIVEL0)

**Scope**: Metadatos de posiciones actualmente abiertas. NIVEL0 SSOT para el monitor de posiciones.

| Column | Type | Purpose |
|--------|------|---------|
| ticket | INTEGER PK | ID de la posición en el broker |
| symbol | TEXT | Instrumento |
| entry_price | REAL | Precio de entrada |
| entry_time | TEXT | Hora de entrada |
| direction | TEXT | `BUY` \| `SELL` |
| sl / tp | REAL | Stop Loss y Take Profit actuales |
| volume | REAL | Tamaño de la posición |
| initial_risk_usd | REAL | Riesgo inicial en USD |
| entry_regime | TEXT | Régimen en el momento de entrada |
| timeframe | TEXT | Marco temporal de la señal |
| strategy | TEXT | Estrategia que generó la señal |
| data | TEXT | JSON con datos adicionales |

---

### `session_tokens` (Auth Session Management — NIVEL0)

**Scope**: Tokens de sesión JWT/Bearer para la API REST.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| token_hash | TEXT UNIQUE | Hash del token (nunca el token en claro) |
| user_id | TEXT | FK → sys_users |
| token_type | TEXT | Tipo de token (`access`, `refresh`) |
| expires_at | DATETIME | Expiración del token |
| revoked | BOOLEAN | Si fue revocado explícitamente |
| created_at / last_used_at | DATETIME | Auditoría de uso |
| user_agent / ip_address | TEXT | Contexto de la sesión |

---

### `usr_broker_accounts` (User Broker Accounts)

**Scope**: Cuentas de broker del ADMIN con límites de riesgo.

| Column | Type | Purpose |
|--------|------|---------|
| id | TEXT PK | UUID |
| user_id | TEXT | FK → sys_users |
| broker_name | TEXT | Nombre del broker |
| broker_account_id | TEXT | ID en el broker |
| account_type | TEXT | `REAL` \| `DEMO` |
| account_status | TEXT | `ACTIVE` \| `SUSPENDED` \| `CLOSED` |
| daily_loss_limit | DECIMAL | Límite de pérdida diaria |
| max_position_size | DECIMAL | Tamaño máximo de posición |
| max_open_positions | INTEGER | Máximo de posiciones abiertas |
| balance / equity | DECIMAL | Última sincronización |
| last_sync_utc | TIMESTAMP | Hora de última sincronización |

---

### Tablas de soporte adicionales

| Tabla | Propósito |
|-------|-----------|
| `usr_anomaly_events` | Anomalías detectadas: Z-Score, Flash Crash, drawdown extremo |
| `usr_coherence_events` | Incoherencias detectadas en señales (CoherenceMonitor) |
| `usr_connector_settings` | Toggle manual de conectores por proveedor |
| `usr_edge_learning` | Registro de aprendizajes del sistema EDGE |
| `usr_notification_settings` | Configuración de canales de notificación |
| `usr_notifications` | Notificaciones generadas para el ADMIN |
| `usr_preferences` | Configuración personal de UI y trading |
| `usr_signal_pipeline` | Auditoría de etapas de procesamiento de señales |
| `usr_strategy_logs` | Logs de rendimiento de estrategias por activo y fecha |
| `usr_tuning_adjustments` | Ajustes aplicados por EdgeTuner |
| `edge_learning` | Legacy — aprendizaje EDGE (pre-convención) |
| `notifications` | Legacy — notificaciones (pre-convención) |

---

## 🔧 PROVISIONING: Templates y Nuevos Tenants

El sistema mantiene una **plantilla maestra** en `data_vault/templates/usr_template.db` que contiene SOLO las tablas `usr_*` (16 tablas). Cuando se crea un nuevo tenant, su BD se clona desde esta plantilla.

**Función**: `bootstrap_tenant_template()` en `data_vault/schema.py`

**Modos**:

| Modo | Comportamiento | Recomendación |
|------|---|---|
| `"manual"` (default) | Solo en llamada explícita | ✅ PRODUCCIÓN |
| `"automatic"` | En cada startup si falta template | Para desarrollo |

**Configuración en `sys_config`**:
- `tenant_template_bootstrap_mode`: `"manual"` o `"automatic"`
- `tenant_template_bootstrap_done`: `"0"` → `"1"` tras completarse

---

## Architecture Summary

| Aspect | Capa 0 (Global) | Capa 1 (Tenant) |
|--------|-----------------|-----------------|
| **Physical Location** | `data_vault/global/aethelgard.db` | `data_vault/tenants/{uuid}/aethelgard.db` |
| **Prefixes** | `sys_*` (26) + legacy (4) | `usr_*` (16) |
| **Write Authority** | Admin/System | Tenant |
| **Read Authority** | Everyone (read-only for tenants) | Tenant (full access) |
| **Has tenant_id Column?** | Algunos (opcional) | NO (inferido del path) |
| **Purpose** | Shared Intelligence | Local Execution |

---

## Naming Convention (Regla de Oro)

✅ **GLOBAL Rule**: `sys_*` = global compartido. `usr_*` = tenant personal.
✅ **Redundancy Rule**: Datos en `sys_*` NUNCA duplicados en `usr_*`; tenants filtran en runtime.
⚠️ **Legacy Exception**: `edge_learning`, `notifications`, `position_metadata`, `session_tokens` preexisten a la convención. No violarla en tablas nuevas.

---

## Data Retention & Future Considerations

- Sin purga automática implementada actualmente
- Future: Archivar trades > 90 días (status CLOSED) a history DB
- Future: `sys_agent_events` — FASE 4A (Sprint 11) para AutonomousSystemOrchestrator

---

## 📋 Changelog de Schema

| Versión | Fecha | Sprint | Cambios |
|---------|-------|--------|---------|
| **v3.2** | **2026-03-25** | **Deuda documental** | **Sincronización total con DB real. 46 tablas documentadas (vs 10 en v3.1). Columnas reales de `usr_assets_cfg`, `usr_trades`, `sys_market_pulse`, `sys_economic_calendar`. Tablas obsoletas eliminadas (`sys_calendar`, `usr_strategies`, `usr_signals`). 5 tablas legacy/infra anotadas. Secciones detalladas para las 46 tablas.** |
| v3.1 | 2026-03-24 | Sprint 9 (E10) | `sys_strategies`: +`required_regime`, +`required_timeframes`, +`execution_params` (HU 7.8). |
| v3.0 | 2026-03-09 | Sprint Arquitectónico | Schema verification ARCH-SSOT-2026-008. Consolidación DDL. |
| v2.x | 2026-03-07 | — | NIVEL0: `sys_signal_ranking`, `session_tokens`, `position_metadata` movidas a `schema.py`. |

**Last Validated**: 2026-03-25
**Architecture Version**: ARCH-SSOT-2026-010 (Full Schema Documentation)
