# BACKLOG - Aethelgard Development

**Version**: 2.0  
**Last Updated**: 2026-03-07  
**Status**: Active Planning

---

## Dominio 08: Data Sovereignty & Persistence

### 8.5: Refactor de Naming de Base de Datos (ARCH-SSOT-2026-006)

**Status**: 📋 PLANNED (Próxima semana)  
**Scope**: Rename internal table names to comply with sys_*/usr_* convention  
**Effort**: 3-4 days  
**Priority**: 🔴 CRITICAL (Architectural Foundation)

**Objective**: Rename all physical tables in `data_vault/schema.py` and update all SQL queries across the codebase to use standardized names.

**Tasks**:
- [ ] 8.5.1: Update `data_vault/schema.py` DDL statements
  - Rename: `system_state` → `sys_config`
  - Rename: `market_state` → `sys_market_pulse`
  - Rename: `economic_calendar` → `sys_calendar`
  - Rename: `instruments_config` → `usr_assets_cfg`
  - Rename: `strategies` → `usr_strategies`
  - Rename: `signals` → `usr_signals`
  - Rename: `trades` → `usr_trades`
  - Rename: `strategy_ranking` → `usr_performance`
  - Update all indexes to match new names (e.g., `idx_sys_config_key`)

- [ ] 8.5.2: Update SQL queries in `data_vault/`
  - Search all `.py` files in `data_vault/` for hardcoded table names
  - Replace all references: `SELECT FROM system_state` → `SELECT FROM sys_config`, etc.
  - Files affected: storage_manager.py, trades_db.py, signals_repository.py, and others

- [ ] 8.5.3: Update schema migrations in `run_migrations()`
  - Verify all ALTER TABLE statements use new names
  - Verify all CREATE INDEX statements reference new table names

- [ ] 8.5.4: Execute schema migration on test DBs
  - Create migration script to rename tables (sqlite3 ALTER TABLE RENAME)
  - Test on non-production instances
  - Verify foreign key constraints intact

- [ ] 8.5.5: Integration testing
  - Run `validate_all.py` (must pass 100%)
  - Run full test suite (tests/ directory)
  - Verify: 0 SQL errors, 0 schema violations

**Acceptance Criteria**:
- ✅ All 10 tables renamed correctly in schema.py
- ✅ All SQL queries in codebase use new names (verified by grep)
- ✅ `validate_all.py` passes 100% (22/22 modules)
- ✅ Tests pass 100% (152+ tests)
- ✅ No hardcoded references to old table names remain

---

### 8.6: Desacoplamiento de Mercado: Global Scanner → sys_market_pulse

**Status**: 📋 PLANNED (Semana siguiente)  
**Scope**: Refactor market_state write logic to centralized global scanner  
**Effort**: 2-3 days  
**Priority**: 🟡 HIGH (Efficiency & Governance)

**Objective**: Move market data writing logic from per-tenant scanner to global scanner (Capa 0) so all traders share a single `sys_market_pulse` data source.

**Current State**:
- Each tenant's scanner writes to its own `market_state` table
- Redundant scans: If 10 traders trade EURUSD, it's scanned 10 times
- Inconsistency: Market state can vary slightly across tenants

**Target State**:
- Global Scanner writes to `sys_market_pulse` (once per asset/timeframe)
- All tenants read from `sys_market_pulse`
- Tenants filter based on `usr_assets_cfg` (what they trade)
- Efficiency: 1 scan instead of N scans

**Tasks**:
- [ ] 8.6.1: Design Global Scanner component
  - Create new class: `GlobalMarketScanner` in `core_brain/`
  - Integrates with MultiTimeframe Limiter
  - Writes exclusively to `sys_market_pulse` in global DB
  - Triggered on boot + interval-based scheduling

- [ ] 8.6.2: Update ScannerEngine integration
  - Modify `ScannerEngine` to delegate market write to GlobalMarketScanner
  - Tenants read from `sys_market_pulse` instead of their local `market_state`
  - Caching layer: Fast read from sys_market_pulse + filter by usr_assets_cfg

- [ ] 8.6.3: Migrate market_state → sys_market_pulse
  - Create migration script to copy existing market_state data to sys_market_pulse
  - Remove per-tenant market_state writes (keep read-only for backward compat)

- [ ] 8.6.4: Update queries in signal generation
  - Change: `SELECT FROM market_state` → `SELECT FROM sys_market_pulse WHERE asset IN (...)`
  - Apply in: `SignalFactory`, `StrategyGatekeeper`, and other signal generators

- [ ] 8.6.5: Testing
  - Unit tests: GlobalMarketScanner behavior (write once, read many)
  - Integration tests: Signal generation with shared market data
  - Performance tests: Confirm latency improvement (1 scan vs N scans)

**Acceptance Criteria**:
- ✅ Global Scanner writes to `sys_market_pulse` only
- ✅ No per-tenant market scans (all read from global)
- ✅ Signal generation reads from `sys_market_pulse`
- ✅ Efficiency metrics: CPU usage reduced by 70%+ for market scanning
- ✅ All tests pass
- ✅ Performance improved (baseline: < 100ms for market data access)

---

## Dominio 04: Risk Governance

### Future Tasks (Planned for Q2 2026)

- [ ] 4.1: Implement Dynamic Risk Adjustment
- [ ] 4.2: Add Correlation-based Position Sizing
- [ ] 4.3: Enhance SIP Monitoring for Multi-Asset Exposure

---

## Dominio 02: Execution & Connectors

### Future Tasks (Planned for Q2 2026)

- [ ] 2.1: NT8 Connector Stabilization
- [ ] 2.2: CCXT Connector Enhancement
- [ ] 2.3: Paper Trader Reliability Improvements

---

## 🗂️ Backlog Priorities

| Priority | Domain | Task | Est. Days |
|----------|--------|------|-----------|
| 🔴 CRITICAL | 08 | 8.5: Database Naming Refactor | 3-4 |
| 🟡 HIGH | 08 | 8.6: Global Market Scanner | 2-3 |
| 🟢 MEDIUM | 04 | Risk Governance Enhancements | TBD |
| 🔵 LOW | 02 | Connector Improvements | TBD |

---

**Last Updated**: 2026-03-07  
**Owner**: Architecture Team  
**Review Cycle**: Weekly
