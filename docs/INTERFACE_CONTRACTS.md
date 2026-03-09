# INTERFACE CONTRACTS - Aethelgard Data Integration

**Version**: 2.0  
**Status**: ACTIVE (2026-03-07)  
**Trace_ID**: ARCH-INTERFACE-CONTRACTS-v2  
**Domain**: 08 (Data Sovereignty) + 04 (Risk Governance) + Naming Convention (sys_ / usr_)

---

## 🏛️ Convención de Nombres: Contrato Obligatorio

Todas las integraciones externas **DEBEN** cumplir con la convención de nombres:

- **`sys_*`**: Tablas globales en `data_vault/global/aethelgard.db`
- **`usr_*`**: Tablas personalizadas por trader en `data_vault/tenants/{uuid}/aethelgard.db`

**Violación de convención**: ❌ Será rechazada en `validate_all.py` (script: `audit_table_naming.py`)

---

## 🚪 Contract 1: Economic Calendar Injection Gate (Global Data)

**Purpose**: Guarantee data integrity for economic events before persistence to **`sys_calendar`** table (renamed from economic_calendar).

**Scope**: All external economic data (Bloomberg, Investing.com, ForexFactory) entering the system.

**Responsibility**: NewsSanitizer component validates and transforms raw external data to system-compatible format. Data is **shared globally** (read-only for traders).

---

## 📋 Input/Output Contract

| Aspect | Raw Data (Untrusted) | Validated Data (Trusted) |
|--------|----------------------|--------------------------|
| **Source** | External provider (Bloomberg, Investing.com, etc.) | NewsSanitizer output |
| **Destination** | N/A | **`sys_calendar`** (global, read-only for traders) |
| **Guarantee** | None (may contain errors, duplicates, malformed fields) | Schema-valid, latency-checked, immutable-ready |
| **Responsibility** | Provider | NewsSanitizer validates |

---

## 🔐 Three Pillars of Data Validation

### Pilar 1️⃣: SCHEMA VALIDATION
**Mandatory Fields**:
- `event_name`: Non-empty string
- `country`: ISO 3166-1 alpha-2 code (USA, EUR, GBR, JPY, etc.) — must be normalized
- `impact_score`: ENUM only (HIGH | MEDIUM | LOW) — no numeric, no free-text alternatives
- `event_time_utc`: Valid UTC timestamp (parseable to datetime, not malformed)
- `currency`: ISO 4217 code (USD, EUR, GBP, JPY, etc.)

**Validation Gates**:
- If any mandatory field missing or invalid → REJECT with DataSchemaError
- Normalizer must convert free-text impact ("Alto", "3", "High Impact") to standard ENUM
- Normalizer must convert country names to ISO codes ("United States" → "USA")
- Normalizer must parse timestamps to UTC (handle timezone conversions if needed)
- If parsing fails → REJECT with DataSchemaError

**Failure Action**: Log warning with event details, skip record, continue processing next event.

---

### Pilar 2️⃣: LATENCY VALIDATION
**Age Window**:
- Accept events with `event_time_utc` from NOW() - 30 days to NOW() + 30 days
- Reject events older than 30 days (considered stale, not useful)
- Allow future events (forecasted economic releases are valid)

**Validation Gates**:
- Calculate age: (NOW() - event_time_utc) in days
- If age > 30 days → REJECT with DataLatencyError
- If age is negative (future) AND < 30 days forward → ACCEPT (valid forecast)

**Failure Action**: Log warning with event age in days, skip record, continue.

**Rationale**: Prevent table bloat with historical events; maintain focus on recent/upcoming events only.

---

### Pilar 3️⃣: IMMUTABILITY ENFORCEMENT
**After Data Enters the Table**:
- Once `event_id` is assigned and data is persisted → **NO UPDATES ALLOWED**
- Runtime prohibition: `UPDATE sys_economic_calendar SET ...` is NOT permitted
- If data needs correction → INSERT new event with new `event_id`, keep old record as historical audit trail

**Enforcement Mechanism**:
- StorageManager methods must enforce: `update_economic_event()` raises `OperationNotAllowedError`
- Schema: `event_id` is UNIQUE PRIMARY KEY (prevents duplicates)
- Append-only design: corrections = new inserts, never modifications

**Rationale**: Guarantee that historical economic data cannot be "revised" after the fact, maintaining audit trail integrity.

---

## 🏷️ Data Fields (System Contract) - `sys_economic_calendar` Table

| Field | Type | Source | Validation | Immutable |
|-------|------|--------|-----------|-----------|
| `event_id` | UUID | System-generated (not from provider) | Unique, non-null | ✅ Yes |
| `provider_source` | String | Raw data | Must be: BLOOMBERG, INVESTING, FOREXFACTORY | ✅ Yes |
| `event_name` | String | Raw data | Non-empty, max 255 chars | ✅ Yes |
| `country` | String (ISO 3166-1) | Raw data → Normalized | Must be ISO code (USA, EUR, etc.) | ✅ Yes |
| `currency` | String (ISO 4217) | Raw data → Normalized | Must be ISO code (USD, EUR, etc.) | ✅ Yes |
| `impact_score` | Enum | Raw data → Normalized | ENUM: HIGH, MEDIUM, LOW only | ✅ Yes |
| `forecast` | Decimal | Raw data | Numeric, nullable | ✅ Yes |
| `actual` | Decimal | Raw data | Numeric, nullable | ✅ Yes |
| `previous` | Decimal | Raw data | Numeric, nullable | ✅ Yes |
| `event_time_utc` | Timestamp | Raw data → Parsed | Valid UTC timestamp | ✅ Yes |
| `is_verified` | Boolean | System | Default False, set True after sanitization | ❌ Mutable (once) |
| `data_version` | Integer | System | Version schema (1, 2, 3...) for migrations | ❌ Mutable (on schema updates) |
| `created_at` | Timestamp | System | Auto-generated on INSERT | ✅ Yes |

---

## 2️⃣ Contract 2: Risk Manager Global Limits vs User Overrides

**Purpose**: Enforce **global hard-stops** (`sys_state`) while allowing trader customization (`usr_strategy_params`).

**Scope**: Daily risk limits, max drawdown, consecutive loss stops.

**Responsibility**: RiskManager queries BOTH levels and applies most restrictive rule.

| Parameter | Table (Global) | Table (User) | Decision Logic |
|-----------|---|---|---|
| **max_daily_risk_pct** | `sys_state` (key=max_daily_risk_pct) | `usr_strategy_params` (if exists) | Use MIN(sys_value, usr_value) |
| **max_consecutive_losses** | `sys_state` | `usr_strategy_params` | Use MIN(sys_value, usr_value) |
| **max_drawdown_pct** | `sys_state` | `usr_strategy_params` | Use MIN(sys_value, usr_value) |

**Implementation Pattern**:
```python
# RiskManager.__init__()
def evaluate_signal(self, signal: OutputSignal, trader_id: str) -> RiskResult:
    # 1. Obtener límites globales (sys_)
    global_db = StorageManager.get_global_db()
    global_limits = global_db.query("SELECT value FROM sys_state WHERE key LIKE 'max_%'")
    
    # 2. Obtener límites personalizados (usr_)
    trader_db = TenantDBFactory.get_storage(trader_id)
    user_limits = trader_db.query("SELECT * FROM usr_strategy_params WHERE trader_id=?", trader_id)
    
    # 3. Aplicar el más restrictivo (MIN)
    effective_limit = min(global_limits.max_daily_risk, user_limits.max_daily_risk or global_limits.max_daily_risk)
    
    # 4. Evaluación
    if current_risk > effective_limit:
        return RiskResult.REJECTED(reason="Exceeds effective daily risk limit")
    
    return RiskResult.APPROVED()
```

---

## 3️⃣ Contract 3: Signal Generation with sys_ Knowledge + usr_ Filtering

**Purpose**: UniversalEngine genera señales basado en datos globales, pero filtra por configuración personal.

**Scope**: Strategy availability, asset whitelist, membership tier.

**Responsibility**: SignalFactory queries sys_ for strategy metadata, then filters by usr_ config.

| Data Level | Table | What | Who Writes | Who Reads |
|---|---|---|---|---|
| **Global** | `sys_strategies` | Estrategia disponible, readiness, metadata | DevOps | System, Trader (readonly) |
| **Personal** | `usr_assets_cfg` | Qué activos permite trader, filtros personalizados | Trader | System, Trader |
| **Output** | `usr_signals` | Señales generadas (filtradas) | System | Trader, Admin (audit) |

**Implementation Pattern**:
```python
# SignalFactory.generate_signals()
async def generate_signals(self, trader_id: str) -> List[OutputSignal]:
    """
    Genera señales filtrando sys_ (global) contra usr_ (personal)
    """
    
    # 1. Cargar estrategias globales disponibles
    global_db = StorageManager.get_global_db()
    strategies = global_db.query("SELECT * FROM sys_strategies WHERE readiness='READY_FOR_ENGINE'")
    
    # 2. Cargar configuración personal del trader
    trader_db = TenantDBFactory.get_storage(trader_id)
    user_config = trader_db.query("SELECT * FROM usr_assets_cfg WHERE enabled=1")
    
    signals = []
    for strategy in strategies:
        for symbol in user_config:
            # 3. Generar solo si estrategia es global + trader lo permite
            if strategy.market_whitelist contains symbol.symbol:
                signal = await strategy.engine.analyze(symbol, market_data)
                if signal:
                    # 4. Guardar en usr_signals
                    trader_db.write("INSERT INTO usr_signals (...) VALUES (...)")
                    signals.append(signal)
    
    return signals
```

---

## ✅ Validation Checklist (Para cada integración externa)

- [ ] **Tabla destino usa prefijo correcto** (sys_* o usr_*?)
- [ ] **SCHEMA VALIDATION** ejecutado (mandatory fields presentes y válidos)
- [ ] **LATENCY VALIDATION** ejecutado (evento no demasiado viejo)
- [ ] **IMMUTABILITY** garantizada (no hay UPDATE después de INSERT)
- [ ] **Redundancia verificada** (NO duplicar sys_ en usr_)
- [ ] **Access control** implementado (Trader no escribe sys_, System no accede usr_credentials)
- [ ] **TRACE_ID** presente en logs de transformación
- [ ] Datos integrados pasan `audit_table_naming.py` script

---

---

## 📊 Workflow: Raw Data → Persistence

| Step | Component | Input | Validation | Output | Failure Action |
|------|-----------|-------|-----------|--------|-----------------|
| 1 | Provider | External API | None | Raw event object | - |
| 2 | NewsSanitizer | Raw event | Schema validation | Normalized event (country/impact/timestamp fixed) | REJECT, log DataSchemaError |
| 3 | NewsSanitizer | Normalized event | Latency check | Age check result | REJECT, log DataLatencyError |
| 4 | NewsSanitizer | Validated event | Generate UUID | event_id (system-assigned) | Auto-generate |
| 5 | StorageManager | Complete event | is_verified=False | INSERT into table | If INSERT fails → REJECT, log error |
| 6 | Post-Sanitization | Inserted record | Read-only enforcement | economic_calendar (IMMUTABLE) | UPDATE attempts → Exception |

---

## ⚠️ Error Categories

| Error Type | Cause | Log Level | Action |
|-----------|-------|-----------|--------|
| `DataSchemaError` | Missing field, invalid country code, unparseable timestamp | WARNING | Skip record, continue batch |
| `DataLatencyError` | Event age > 30 days | WARNING | Skip record, continue batch |
| `DataIncompatibilityError` | Data cannot be reconciled (e.g., impact value impossible to normalize) | ERROR | Skip record, escalate to admin |
| `PersistenceError` | Database INSERT fails | ERROR | Log detailed error, skip record |
| `ImmutabilityViolation` | UPDATE attempt on immutable record | ERROR | Raise exception, abort operation |

**Logging Requirement**:
- Every rejection must log: event source, reason, timestamp
- Every successful insertion must log: event_id, provider_source, impact_score
- Batch summaries must log: X events processed, Y accepted, Z rejected

---

## 🧪 Testing Requirements

**Mandatory Test Coverage**:

1. **Schema Validation Tests**:
   - Valid country codes accepted (USA, EUR, GBR, JPY, etc.)
   - Invalid country codes rejected (INVALID, XYZ, etc.)
   - Missing `event_name` rejected
   - Missing `impact_score` rejected
   - Impact normalization: "HIGH", "Alto", "3" → all become HIGH enum

2. **Latency Validation Tests**:
   - Event from 5 days ago: ACCEPTED
   - Event from 30 days ago: ACCEPTED
   - Event from 31 days ago: REJECTED (DataLatencyError)
   - Event from future (forecast): ACCEPTED if < 30 days forward

3. **Immutability Tests**:
   - INSERT new event: SUCCESS
   - UPDATE existing event: ERROR (ImmutabilityViolation)
   - INSERT same event_id twice: REJECTED (uniqueness constraint)

4. **UUID Generation Tests**:
   - event_id from provider ignored (system generates own)
   - Generated event_id is unique across batch
   - event_id format is valid UUID v4

5. **Batch Processing Tests**:
   - Bad records don't block good records
   - Rejection count accurate
   - Acceptance count accurate
   - Partial failure handled gracefully

---

## 🔒 Security & Data Governance

**Agnosis Principle**: NewsSanitizer must NOT assume provider format.
- Transforms to standard internal format
- Works with any provider (Bloomberg, Investing.com, etc.)
- Supports new providers without code changes

**Single Source of Truth (SSOT)**: economic_calendar table is the ONLY source of truth for economic events after sanitization.
- JSON seeds/config files are NOT used for runtime economic data
- All queries to FundamentalGuardService read from economic_calendar table
- Updates to economic data flow through NewsSanitizer gate only

**Immutability Guarantee**: Once data is in the table, it cannot be silently revised.
- Audit trail preserved (original created_at)
- Corrections are new inserts with new event_id
- Compliance: No retroactive data manipulation

---

## 📌 Implementation Prerequisites

Before Executor implements NewsSanitizer:

✅ **Documentation** (this file): Contract approved and available  
✅ **Schema approval**: DDL for economic_calendar table must be proposed separately  
✅ **Test cases**: Test suite must cover all 5 test categories above  
✅ **Error definitions**: DataSchemaError, DataLatencyError, etc. classes defined  
✅ **Logging specification**: Log format, required fields, batch reporting defined  
✅ **Country/Currency mappers**: ISO 3166-1 and 4217 lookup tables available  

---

## 🎯 Success Criteria

| Criterion | Measurement |
|-----------|-------------|
| No corrupted data | Zero DataSchemaErrors in production (pre-insertion detection works) |
| No stale data | Zero events > 30 days old in table |
| Immutability maintained | Zero successful UPDATE operations on economic_calendar |
| Agnosis preserved | Works with provider_source: BLOOMBERG, INVESTING, FOREXFACTORY |
| Traceability | Every event logged with source, impact_score, event_id |
| Performance | Batch processing < 50ms per event (latency check + schema validation) |

---

## � Contract 2: Economic Veto Interface (NEWS BUFFER GATE)

**Purpose**: Provide trading system (MainOrchestrator) with single source of truth about whether it's safe to trade a given symbol, considering economic calendar events.

**Scope**: All trading decisions in MainOrchestrator that involve currency pairs affected by economic news.

**Responsibility**: EconomicIntegrationManager (via get_trading_status) consults economic_calendar and applies News Buffers.

---

### **Contract Definition: EconomicVetoInterface**

```python
class EconomicVetoInterface:
    """
    Trading system queries economic safety before opening/managing positions.
    NOT about managing the scheduler - only about trading permission.
    """
    
    async def get_trading_status(
        self, 
        symbol: str,  # e.g., "EURUSD", "GBPUSD", "USDJPY"
        current_time: datetime = None
    ) -> Dict[str, Any]:
        """
        Is it safe to trade this symbol RIGHT NOW?
        
        Returns:
        {
            'is_tradeable': bool,  # False if inside impact buffer
            'reason': str,         # "HIGH impact news (NFP) in 10 min buffer"
            'next_event': Dict,    # Upcoming event details (if blocked)
            'affected_pairs': [str],    # [EURUSD, GBPUSD] if any
            'buffer_start': datetime,   # When the buffer started
            'buffer_end': datetime,     # When buffer ends
            'impact_level': str    # HIGH|MEDIUM|LOW
        }
        """
```

### **Buffer Logic (Pre/Post News)**

| Impact | Pre-Buffer | Post-Buffer | Action |
|--------|-----------|------------|--------|
| **HIGH** | 15 min before | 10 min after | ❌ NO new positions, manage existing (Break-Even or close) |
| **MEDIUM** | 5 min before | 3 min after | ⚠️ CAUTION - reduce size 50% |  
| **LOW** | 0 min before | 0 min after | ✅ Normal trading |

### **Symbol Mapping**

Economic events affect currencies. Mapping:
- **NFP (US Jobs)** → `USD` pairs: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD
- **ECB Interest Rate** → `EUR` pairs: EURUSD, EURGBP, EURJPY
- **BOE Decision** → `GBP` pairs: GBPUSD, EURGBP, GBPJPY
- **RBA Statement** → `AUD` pairs: AUDUSD, EURADD
- **BOJ News** → `JPY` pairs: USDJPY, EURJPY, GBPJPY

### **Implementation Requirements**

1. **Real-time Query**: `get_trading_status(symbol)` must run in < 50ms
2. **Caching**: Cache results for 60 seconds to avoid repeated DB queries
3. **Graceful Degradation**: If economic_calendar down, return `is_tradeable=True` (fail open, let trading continue)
4. **Agnosis Maintained**: MainOrchestrator doesn't know about Investing.com; only asks manager
5. **Logging**: Every veto decision logged with trace_id

### **Success Criteria**

| Criterion | Measurement |
|-----------|-------------|
| Correct symbol mapping | USD pairs blocked during HIGH US events |
| Buffer timing | Pre/post buffers respected (±30 sec tolerance) |
| Performance | Response time < 50ms |
| Agnosis | MainOrchestrator zero knowledge of provider sources |
| Graceful degradation | System continues if economic data unavailable |
| Traceability | Every veto decision has trace_id |

---

## 📍 References

- **DEVELOPMENT_GUIDELINES.md**: Section 3 (Data Sanitization Rules)
- **AETHELGARD_MANIFESTO.md**: Section IV.A (Gestión de Credenciales — applies immutability principle) + Section VIII (Veto por Calendario)
- **core_brain/services/fundamental_guard.py**: Consumer of economic_calendar data
- **core_brain/economic_integration.py**: Implementation of EconomicVetoInterface
- **SYSTEM_LEDGER.md**: Register any schema changes here

---

**End of Contracts v1.0**

