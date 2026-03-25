# Aethelgard Database Schema v3.1 (ARCH-SSOT-2026-009)

## Overview

**Database Engine**: SQLite 3 (Idempotent, Multi-Tenant Capable)
**Architecture**: Unified Global DB + Tenant Templates
**Current Status**: Single Admin in Global DB (No Active Tenants)
**Initialization**: Pure DDL via `data_vault/schema.py` + Migrations
**Source of Truth**: This document + Global DB (`data_vault/global/aethelgard.db`)
**Last Updated**: 2026-03-24 (Sprint 9 — E10 Motor de Backtesting Inteligente)

⚠️ **CONTRATO ARQUITECTÓNICO FINAL**: Esta estructura es vinculante. La DB global es la ÚNICA FUENTE DE VERDAD en operación.

---

## 🗂️ ARQUITECTURA ACTUAL (Real)

| DB | Contenido | Propósito | Tablas |
|----|-----------|----------|--------|
| **data_vault/global/aethelgard.db** | sys_* + usr_* | ADMIN principal (datos globales + personales) | 30+ tablas |
| **data_vault/templates/usr_template.db** | usr_* | Plantilla para clonar nuevos tenants | 20+ tablas |
| **data_vault/tenants/{uuid}/** | (vacío) | Cuando se cree un nuevo usuario, se clonará template aquí | - |

---

## ✅ CAPA GLOBAL: ADMIN DATABASE (`data_vault/global/aethelgard.db`)

## ✅ CAPA GLOBAL: ADMIN DATABASE (`data_vault/global/aethelgard.db`)

### Contenido Actual (Real - 24 Marzo 2026):

**TABLAS SYS_* (Compartidas - Global)**: 26 tablas
```
sys_audit_logs                   - Auditoría de acciones y transiciones de modo (SYSTEM user)
sys_broker_accounts              - Configuración de cuentas de broker
sys_brokers                      - Metadatos de brokers
sys_config                       - Configuración del sistema (SSOT)
sys_consensus_events             - Eventos de consenso multi-estrategia
sys_cooldown_tracker             - Control de cooldown de señales por estrategia/par
sys_credentials                  - Credenciales encriptadas
sys_data_providers               - Proveedores de datos (DB-driven, incluye connector_module/class)
sys_dedup_events                 - Eventos de deduplicación de señales
sys_dedup_rules                  - Reglas de deduplicación configurables
sys_economic_calendar            - Calendario económico
sys_execution_feedback           - Feedback de ejecución (rejection logger — NIVEL0 SSOT)
sys_market_pulse                 - Estado del mercado (global scanner)
sys_platforms                    - Plataformas de trading
sys_regime_configs               - Configuración de regímenes de mercado
sys_shadow_instances             - Instancias activas en modo SHADOW (lifecycle HU 7.3)
sys_shadow_performance_history   - Historial de evaluación de instancias SHADOW (3 Pilares)
sys_shadow_promotion_log         - Log de promociones SHADOW → LIVE
sys_signal_pipeline              - Auditoría de señales
sys_signal_quality_assessments   - Evaluaciones de calidad de señales (SignalQualityScorer)
sys_signal_ranking               - Ranking global de estrategias (formerly usr_performance)
sys_signals                      - Señales generadas globales
sys_strategies                   - Registro de estrategias disponibles (ver detalle abajo)
sys_strategy_logs                - Logs de ejecución de estrategias
sys_symbol_mappings              - Mapeo de símbolos (SSOT)
sys_users                        - Usuarios del sistema
```

**TABLAS USR_* (Personales del ADMIN)**: 12 tablas
```
usr_anomaly_events               - Eventos de anomalías detectadas
usr_assets_cfg                   - Activos que ADMIN opea
usr_coherence_events             - Eventos de incoherencia de señales
usr_connector_settings           - Configuración de conectores
usr_edge_learning                - Aprendizaje EDGE del sistema
usr_execution_logs               - Logs de ejecución de órdenes
usr_notification_settings        - Configuración de notificaciones
usr_notifications                - Notificaciones del sistema
usr_position_history             - Historial de posiciones
usr_preferences                  - Preferencias del usuario ADMIN
usr_trades                       - Ejecuciones/trades del ADMIN
usr_tuning_adjustments           - Ajustes de tuning del sistema
```

**OTRAS TABLAS**: 4 tablas (Sistema/Legacy)
```
edge_learning            - Tabla de aprendizaje EDGE (legacy)
position_metadata        - Metadatos de posiciones abiertas (monitoreo — NIVEL0 SSOT)
session_tokens          - Tokens de sesión (auth — NIVEL0 SSOT)
sqlite_sequence         - Secuencia de SQLite
```

> ⚠️ **NIVEL0 NOTA**: `notifications` (Tablas legacy) fue renombrada a `usr_notifications` (ya listada en USR_* arriba). `session_tokens` movida de session_manager.py a schema.py. `position_metadata` movida de trades_db.py a schema.py.

---

### `sys_config` (Global Configuration SSOT)

---

### `sys_market_pulse` (Global Market Intelligence, READ-ONLY)

**Scope**: Global market snapshot cache (per asset, per timeframe).  
**Governance**: ⭐ Global Scanner writes; all tenants read only.  
**Query Pattern**: Tenants filter by their own assets in usr_assets_cfg.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Record ID |
| asset | TEXT | Trading instrument (use "asset" terminology) |
| timeframe | TEXT | Candle period (M5, H1, D1) |
| open | REAL | Candle open price |
| high | REAL | Candle high price |
| low | REAL | Candle low price |
| close | REAL | Candle close price |
| volume | REAL | Trading volume |
| indicators | TEXT | JSON: RSI, MACD, Bollinger Bands, etc. |
| regime | TEXT | Market regime (TREND, RANGE, VOLATILE, SHOCK) |
| snapshot_at | TIMESTAMP | Candle close time |

**Indexes**:
- `idx_sys_market_pulse_asset_timeframe` on (asset, timeframe)
- `idx_sys_market_pulse_snapshot_at` on snapshot_at

---

### `sys_calendar` (Global Economic Calendar)

**Scope**: Global shared economic events (NFP, BCE, etc.).  
**Governance**: NewsSanitizer writes; tenants read only.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Event ID |
| event_name | TEXT | Event name (must be validated) |
| country | TEXT | ISO 3166-1 alpha-2 code (USA, EUR, GBR) |
| impact_score | TEXT | ENUM (HIGH, MEDIUM, LOW) |
| event_time_utc | TIMESTAMP | Event time in UTC |
| currency | TEXT | ISO 4217 code (USD, EUR, GBP) |
| created_at | TIMESTAMP | Record creation |

**Indexes**: `idx_sys_calendar_country` on country, `idx_sys_calendar_event_time` on event_time_utc

---

### `sys_strategies` (Strategy Registry — Lifecycle + Backtesting)

**Scope**: Global registry of all trading strategies. Controls the lifecycle pipeline BACKTEST → SHADOW → LIVE.
**Governance**: Admin/System writes; all components read.
**Migration**: Idempotent — `run_migrations()` in `data_vault/schema.py` adds columns safely.

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| class_id | TEXT PK | — | Unique strategy identifier (e.g. `MOM_BIAS_0001`) |
| mnemonic | TEXT | — | Short human-readable name |
| version | TEXT | — | Semantic version |
| description | TEXT | — | Strategy description |
| type | TEXT | — | Strategy type (PYTHON_CLASS, etc.) |
| class_file | TEXT | — | Python module path |
| class_name | TEXT | — | Python class name |
| required_sensors | TEXT | `[]` | JSON array of required sensor IDs |
| logic | TEXT | — | Logic description |
| affinity_scores | TEXT | `{}` | JSON: empirical performance evidence (darwin ranking) |
| market_whitelist | TEXT | `[]` | JSON array of allowed assets |
| readiness | TEXT | — | Readiness level |
| readiness_notes | TEXT | — | Notes on readiness |
| mode | TEXT | `BACKTEST` | Lifecycle mode: `BACKTEST` \| `SHADOW` \| `LIVE` \| `DISABLED` |
| score_backtest | REAL | `0.0` | Score from ScenarioBacktester (AptitudeMatrix.overall_score) |
| score_shadow | REAL | `0.0` | Score from SHADOW evaluation (3 Pilares) |
| score_live | REAL | `0.0` | Score from live trading |
| score | REAL | `0.0` | Consolidated score: `live×0.50 + shadow×0.30 + backtest×0.20` |
| last_backtest_at | TIMESTAMP | NULL | Timestamp of last completed backtest (cooldown reference) |
| created_at | TIMESTAMP | NOW | Registration timestamp |
| updated_at | TIMESTAMP | NOW | Last modification |
| **required_regime** | TEXT | `'ANY'` | ⭐ **HU 7.8** — Regime filter: `TREND` \| `RANGE` \| `VOLATILE` \| `ANY` |
| **required_timeframes** | TEXT | `'[]'` | ⭐ **HU 7.8** — JSON array of required timeframes (e.g. `["M5","M15"]`). Empty = discover empirically |
| **execution_params** | TEXT | `'{}'` | ⭐ **HU 7.8** — JSON with `confidence_threshold`, `risk_reward`. Frees `affinity_scores` for pure empirical use |

> ⭐ **Sprint 9 (HU 7.8)** — Columnas `required_regime`, `required_timeframes`, `execution_params` agregadas 2026-03-24 vía migración idempotente. Migration: `PRAGMA table_info` check + `ALTER TABLE ... ADD COLUMN` en `run_migrations()`.

**Score Formula** (EXEC-V5-STRATEGY-LIFECYCLE-2026-03-23):
```
score = score_live × 0.50 + score_shadow × 0.30 + score_backtest × 0.20
```

**Lifecycle Pipeline**:
```
BACKTEST ──(score_backtest ≥ 0.75)──→ SHADOW ──(3 Pilares pass)──→ LIVE
```

**Backtesting (Sprint 9 — E10)**:
- `BacktestOrchestrator._build_strategy_for_backtest(class_id)` instancia la clase Python con `_NullDep` (sin dependencias externas)
- `ScenarioBacktester._evaluate_slice()` despacha a `strategy.evaluate_on_history(df, params)` si `strategy_instance` está disponible
- Clusters sin datos reales se marcan `is_real_data=False` → `regime_score=0.0` (sin síntesis gaussiana en producción, HU 7.11)

---

### `sys_audit_logs` (Operational Audit Trail)

**Scope**: Auditoría de acciones de sistema y transiciones de modo operacional.
**Governance**: System writes; admin reads.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER PK | Auto-increment |
| user_id | TEXT NOT NULL | `SYSTEM` para eventos de sistema, UUID para acciones de usuario |
| action | TEXT | Tipo de evento (e.g. `MODE_TRANSITION`, `STRATEGY_PROMOTED`) |
| resource | TEXT | Componente origen (e.g. `OperationalModeManager`) |
| resource_id | TEXT | ID del recurso afectado (opcional) |
| old_value | TEXT | Estado anterior |
| new_value | TEXT | Estado nuevo |
| status | TEXT | `OK` \| `ERROR` |
| reason | TEXT | Razón del evento (opcional) |
| timestamp | TEXT | ISO8601 UTC timestamp |
| trace_id | TEXT | ID de trazabilidad (opcional) |

> ⭐ **Sprint 9 (HU 10.7)** — `OperationalModeManager` escribe `MODE_TRANSITION` en esta tabla cuando cambia el contexto operacional (`BACKTEST_ONLY` / `SHADOW_ACTIVE` / `LIVE_ACTIVE`). `user_id='SYSTEM'` para eventos autónomos.

---

### Other Global Tables (sys_auth, sys_memberships, etc.)

These follow the same pattern: admin-managed, read-only for tenants.

---

## 🔧 PROVISIONING: Templates y Nuevo Tenants

### Template Generation (Manual - Recomendado)

El sistema mantiene una **plantilla maestra** en `data_vault/templates/usr_template.db` que contiene SOLO las tablas `usr_*`. Cuando se crea un nuevo tenant, su BD se clona desde esta plantilla.

**Función**: `bootstrap_tenant_template()` en `data_vault/schema.py`

```python
from data_vault.schema import bootstrap_tenant_template
from data_vault.storage import StorageManager

# Obtener conexión global
storage = StorageManager()  # Sin user_id = global
global_conn = storage._get_conn()

# Crear template (MANUAL - recomendado)
bootstrap_tenant_template(global_conn, mode="manual")
```

**Modos de Ejecución**:

| Modo | Comportamiento | Recomendación |
|------|---|---|
| `"manual"` (default) | Solo se ejecuta si se llama explícitamente | ✅ RECOMENDADO |
| `"automatic"` | Se ejecuta en cada startup | Para desarrollo |

**Configuración Persistente**:
- Se guarda en `sys_config` tabla
  - `tenant_template_bootstrap_mode`: "manual" o "automatic"
  - `tenant_template_bootstrap_done`: "1" si ya completado

**Idempotencia**:
```
Si template ya existe → No se sobrescribe
Si bootstrap ya ejecutado (manual) → No se repite
```

### Creación de Nuevo Tenant

```python
# El sistema lo hace automáticamente:
storage = StorageManager(user_id="new_user_uuid")
# → Clona template.db a tenants/new_user_uuid/aethelgard.db
# → Inicializa schema si necesario
```

---

⚠️ **IMPORTANT**: Tenant ID is inferred from the database path. Do NOT store `tenant_id` column in these tables (redundant, violates sovereignty).

### `usr_assets_cfg` (Your Asset Configuration)

**Scope**: Personal asset configuration (what YOU trade).  
**Ownership**: Tenant owns this; can CRUD own assets.  
**Location**: Inferred by DB path (no tenant_id column needed).

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Config ID |
| asset | TEXT | Asset identifier (EURUSD, AAPL, BTCUSDT) - UNIQUE |
| asset_class | TEXT | FOREX, CRYPTO, EQUITY, FUTURES, COMMODITY |
| enabled | BOOLEAN | Category enabled |
| active | BOOLEAN | Individual asset active (default=1) |
| timeframe | TEXT | Primary timeframe (M5, H1, D1) |
| min_qty | REAL | Minimum lot size |
| max_qty | REAL | Maximum lot size |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last modification |

**Indexes**:
- `idx_usr_assets_cfg_asset` on asset
- `idx_usr_assets_cfg_enabled_active` on (enabled, active)

---

### `usr_strategies` (Your Strategies)

**Scope**: Personal strategy registry (definitions, parameters, performance tags).  
**Ownership**: Tenant owns; can activate/deactivate.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Strategy ID |
| strategy_name | TEXT | Unique name (UNIQUE) |
| description | TEXT | Human-readable description |
| file_path | TEXT | Path to strategy module |
| signal_types | TEXT | JSON: ["MEAN_REVERSION", "MOMENTUM"] |
| assets | TEXT | JSON: ["EURUSD", "GBPUSD"]  (use "assets" not "symbols") |
| execution_mode | TEXT | LIVE, SHADOW, DEMO, BACKTEST |
| status | TEXT | ENABLED, DISABLED, TESTING, DEPRECATED |
| enabled_for_live_trading | BOOLEAN | Allowed for real trading |
| affinity_score | REAL | Darwin ranking/priority (0-1) |
| min_win_rate | REAL | Required win rate threshold |
| created_at | TIMESTAMP | Registration timestamp |
| updated_at | TIMESTAMP | Last modification |

**Indexes**:
- `idx_usr_strategies_strategy_name` on strategy_name
- `idx_usr_strategies_status` on status

---

### `usr_signals` (Your Signals)

**Scope**: Personal signal generation records (generation → validation → execution).  
**Ownership**: Tenant owns entire lifecycle.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Signal ID |
| asset | TEXT | Trading pair (use "asset" terminology) |
| timeframe | TEXT | Candle period |
| signal_type | TEXT | BUY, SELL, NEUTRAL |
| strategy_id | INTEGER | Associated strategy |
| confidence | REAL | Signal strength (0-1) |
| status | TEXT | PENDING, VALIDATED, EXECUTED, REJECTED, EXPIRED |
| validation_result | TEXT | JSON: coherence scores, conflict analysis |
| execution_id | INTEGER | Link to actual trade (FK: usr_trades.id) |
| generated_at | TIMESTAMP | Signal creation |
| expires_at | TIMESTAMP | Signal TTL |
| trace_id | TEXT | Traceability ID (DEBUG) |
| metadata | TEXT | JSON: additional context |

**Indexes**:
- `idx_usr_signals_asset_timeframe` on (asset, timeframe)
- `idx_usr_signals_status` on status
- `idx_usr_signals_trace_id` on trace_id

**Relationships**: FK → usr_trades.id

---

### `usr_trades` (Your Trade History)

**Scope**: Personal trade execution history (Soberanía Total del Tenant).  
**Ownership**: Tenant own complete trade lifecycle, P&L, settlement.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Trade ID |
| signal_id | INTEGER | Originating signal |
| asset | TEXT | Trading pair (use "asset" terminology) |
| timeframe | TEXT | Entry timeframe |
| entry_price | REAL | Entry price |
| exit_price | REAL | Exit price (NULL if open) |
| quantity | REAL | Position size |
| direction | TEXT | LONG or SHORT |
| pnl_pips | REAL | P&L in pips |
| pnl_money | REAL | P&L in account currency |
| status | TEXT | OPEN, CLOSED, CANCELED, REJECTED |
| execution_mode | TEXT | LIVE, SHADOW, DEMO, BACKTEST |
| provider | TEXT | Broker (MT5, NT8, PAPER, etc.) |
| account_type | TEXT | REAL or DEMO |
| commission | REAL | Trading commission |
| slippage_pips | REAL | Actual slippage |
| entry_at | TIMESTAMP | Entry execution time |
| exit_at | TIMESTAMP | Exit execution time |
| trace_id | TEXT | Traceability ID |
| metadata | TEXT | JSON: order details, risk calc |

**Indexes**:
- `idx_usr_trades_asset_status` on (asset, status)
- `idx_usr_trades_entry_at` on entry_at
- `idx_usr_trades_execution_mode` on execution_mode

**Relationships**: FK → usr_signals.id

---

### `usr_performance` ~~(Deprecated — Use `sys_signal_ranking`)~~

> ⛔ **DEPRECATED** (ARCH-SSOT-NIVEL0-2026-03-14): Tabla renombrada a `sys_signal_ranking`. La tabla `usr_performance` puede existir en DBs antiguas pero NO se crea en nuevas instalaciones. Ver sección `sys_signal_ranking` arriba.

---

## Architecture Summary

| Aspect | Capa 0 (Global) | Capa 1 (Tenant) |
|--------|-----------------|-----------------|
| **Physical Location** | `data_vault/global/aethelgard.db` | `data_vault/tenants/{uuid}/aethelgard.db` |
| **Prefix** | `sys_*` | `usr_*` |
| **Write Authority** | Admin/System | Tenant |
| **Read Authority** | Everyone (read-only) | Tenant (full access) |
| **Has tenant_id Column?** | Some (optional) | NO (inferred from path) |
| **Purpose** | Shared Intelligence | Local Execution |

---

## Naming Convention (Regla de Oro)

✅ **GLOBAL Rule**: All financial instruments are called `asset` (not `symbol`, not `instrument`).  
✅ **Prefix Rule**: Tables in Capa 0 are `sys_*`, tables in Capa 1 are `usr_*`.  
✅ **Redundancy Rule**: Data in `sys_*` NEVER duplicated in `usr_*`; tenants filter at runtime.

---

## Data Retention & Future Considerations

- No automatic purging currently implemented
- Future: Archive old trades (>90 days, CLOSED status) to history DB
- Future: Time-based partitioning on usr_trades (by entry_at month)
- Future: Tenant-based sharding for large-scale deployments

---

---

## 📋 Changelog de Schema

| Versión | Fecha | Sprint | Cambios |
|---------|-------|--------|---------|
| v3.1 | 2026-03-24 | Sprint 9 (E10) | `sys_strategies`: +`required_regime`, +`required_timeframes`, +`execution_params` (HU 7.8). Lista de tablas actualizada a 26 sys_*. Secciones detalladas: `sys_strategies`, `sys_audit_logs`. |
| v3.0 | 2026-03-09 | Sprint Arquitectónico | Schema verification ARCH-SSOT-2026-008. Consolidación DDL. |
| v2.x | 2026-03-07 | — | NIVEL0: `sys_signal_ranking`, `session_tokens`, `position_metadata` movidas a `schema.py`. |

**Last Validated**: 2026-03-24
**Architecture Version**: ARCH-SSOT-2026-009 (Global Intelligence + Backtesting Framework)

