# Aethelgard Database Schema v2.0 (ARCH-SSOT-2026-006)

## Overview

**Database Engine**: SQLite 3 (Idempotent, Multi-Tenant Capable)  
**Architecture**: Global Intelligence + Local Execution  
**Initialization**: Pure DDL via `data_vault/schema.py`  
**Source of Truth**: This document + schema.py  
**Last Updated**: 2026-03-07 (ARCH-SSOT-2026-006 - Table Naming Standardization)

⚠️ **CONTRATO ARQUITECTÓNICO FINAL**: Esta estructura es vinculante. Cualquier desviación en el código respecto a estos nombres de tablas resultará en fallo de auditoría de arquitectura (`validate_all.py`).

---

## 🗂️ TABLA DE EQUIVALENCIAS: Transformación de Nombres de Tablas

| Tabla Actual (Obsoleta) | Nuevo Nombre (Estandarizado) | DB Física | Alcance | Propósito |
|------------------------|------------------------------|----------|---------|----------|
| system_state | sys_config | global/aethelgard.db | Global | Configuración maestra del motor |
| users_auth | sys_auth | global/aethelgard.db | Global | Credenciales, roles y sesiones |
| memberships | sys_memberships | global/aethelgard.db | Global | Tiers de usuario y acceso |
| market_state | sys_market_pulse | global/aethelgard.db | Global | ⭐ NUEVO: Escaneo único (READ-ONLY para tenants) |
| economic_calendar | sys_calendar | global/aethelgard.db | Global | Eventos macro compartidos |
| instruments_config | usr_assets_cfg | tenants/{id}/aethelgard.db | Tenant | Activos que operas TÚ |
| strategies | usr_strategies | tenants/{id}/aethelgard.db | Tenant | Parámetros personalizados de estrategia |
| signals | usr_signals | tenants/{id}/aethelgard.db | Tenant | Señales en tu cuenta |
| trades | usr_trades | tenants/{id}/aethelgard.db | Tenant | Ejecuciones reales (Soberanía Total) |
| strategy_ranking | usr_performance | tenants/{id}/aethelgard.db | Tenant | Ranking basado en TU equity |

---

## 🔑 Definición de Single Source of Truth (SSOT)

El sistema consulta **sys_market_pulse** (Global Scanner) para descubrir el estado del mercado UNA SOLA VEZ. Cada tenant filtra **sys_market_pulse** contra su propia **usr_assets_cfg** para decidir qué activos operar. Esto garantiza:
- ✅ Eficiencia global (un solo scan del mercado)
- ✅ Soberanía del tenant (operas solo lo que configuraste)
- ✅ SSOT único por nivel (global y tenant)

---

## CAPA 0: GLOBAL INTELLIGENCE (`data_vault/global/aethelgard.db`)

### `sys_config` (Global Configuration)

**Scope**: Global, admin-managed, single source of truth.  
**Governance**: Admin writes; all tenants read.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | System-generated ID |
| key | TEXT | Configuration key name (UNIQUE) |
| value | TEXT | JSON-serialized value |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last modification |

**Indexes**: `idx_sys_config_key` on key

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

### Other Global Tables (sys_auth, sys_memberships, etc.)

These follow the same pattern: admin-managed, read-only for tenants.

---

## CAPA 1: LOCAL EXECUTION (`data_vault/tenants/{tenant_id}/aethelgard.db`)

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

### `usr_performance` (Your Strategy Performance)

**Scope**: Personal strategy ranking (Darwin-style per asset, per execution mode).  
**Ownership**: Tenant owns performance history based on their equity.

| Column | Type | Purpose |
|--------|------|---------|
| id | INTEGER | Rank entry ID |
| strategy_id | INTEGER | Strategy evaluated |
| asset | TEXT | Asset evaluated (use "asset" terminology) |
| timeframe | TEXT | Candle period |
| execution_mode | TEXT | LIVE, SHADOW, DEMO, BACKTEST |
| trades_count | INTEGER | Total trades |
| wins | INTEGER | Winning trades |
| losses | INTEGER | Losing trades |
| win_rate | REAL | Win% (0-1) |
| profit_factor | REAL | Gross Profit / Gross Loss |
| sharpe_ratio | REAL | Risk-adjusted return |
| max_drawdown_pct | REAL | Maximum drawdown % |
| cumulative_pnl | REAL | Total P&L |
| avg_pnl_per_trade | REAL | Average P&L per trade |
| ranking_score | REAL | Composite ranking |
| ranking_date | TIMESTAMP | Calculation date |

**Indexes**:
- `idx_usr_performance_strategy_id` on strategy_id
- `idx_usr_performance_asset` on asset
- `idx_usr_performance_win_rate` on win_rate DESC
- `idx_usr_performance_sharpe` on sharpe_ratio DESC

**Relationships**: FK → usr_strategies.id

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

**Last Validated**: 2026-03-07  
**Architecture Version**: ARCH-SSOT-2026-006 (Global Intelligence + Local Execution)
