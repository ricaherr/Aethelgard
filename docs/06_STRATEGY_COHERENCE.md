# 06_STRATEGY_COHERENCE: Coherence Drift Monitoring (HU 6.3)

**Trace_ID**: COHERENCE-DRIFT-2026-001  
**Status**: ✅ COMPLETED (1-Mar-2026)  
**Version**: 1.0.0  
**Domain**: 06 - Strategy Coherence & Performance Analytics

---

## 📋 Executive Summary

The **CoherenceService** is Aethelgard's self-awareness mechanism for technical drift detection. It continuously compares theoretical performance (Shadow Portfolio) against live execution reality (slippage, latency, execution costs) to answer the critical question:

> *"Is our model coherent with market reality, or is it breaking down?"*

**Mission Statement**: In milliseconds, detect if the system's mathematical assumptions are diverging from operational reality, and emit a **Veto** (block new entries) if coherence falls below institutional thresholds.

---

## 🎯 Core Responsibilities

### 1. Shadow vs. Live Performance Comparison
- **Theoretical Sharpe Ratio**: Ideal conditions (zero slippage, zero latency)
- **Real Sharpe Ratio**: Actual execution with market friction costs
- **Degradation Metric**: How much real performance deviates from expectation

### 2. Slippage & Latency Monitoring
- Extract slippage from execution logs (`execution_shadow_logs` table)
- Calculate volatility of slippage using standard deviation (statistical rigor)
- Track latency distribution to detect infrastructure degradation
- Feed back to Risk Manager for adaptive position sizing

### 3. Coherence Scoring
Coherence = (Performance Coherence × 0.7) + (Latency Coherence × 0.3)

- **Performance Coherence**: Ratio of real Sharpe to theoretical Sharpe
- **Latency Coherence**: Inverse ratio (lower latency = higher coherence)
- **Output**: Score 0-100% with status flags

### 4. Decision Gating (Veto Protocol)
- **COHERENT** (≥80% + <15% degradation): Continue trading
- **MONITORING** (≥80% + ≥15% degradation): Trade with elevated caution
- **INCOHERENT** (<80%): **VETO** - Block new entries, liquidate positions gradually
- **INSUFFICIENT_DATA**: Monitor only, no veto

### 5. Audit Trail & Recovery Detection
- Register all coherence events in `coherence_events` table
- Track recovery trends (slippage improving) to signal resumption of normal operations
- Provide detailed reason strings for operator dashboards

---

## 🏗️ Architecture & Design Patterns

### Dependency Injection (MANDATORY)
```python
# ✅ CORRECT: All dependencies injected
coherence_service = CoherenceService(
    storage=StorageManager(...),  # Database access (SSOT)
    # Thresholds loaded from system_state, not hardcoded
)

# ❌ PROHIBITED: No internal instantiation of dependencies
# coherence_service = CoherenceService()
```

### Configuration Management (SSOT - Single Source of Truth)
**All thresholds stored in `system_state` table**, not hardcoded:

```json
{
  "coherence_config": {
    "min_coherence_threshold": 0.80,           // 80% minimum (tunable)
    "max_performance_degradation": 0.15,       // 15% max allowed
    "min_executions_for_analysis": 5           // Minimum data points
  }
}
```

**Fallback behavior**: If config doesn't exist in DB, service uses safe defaults (80%, 15%, 5).

### File Structure
```
core_brain/
├── services/
│   ├── coherence_service.py          # Main service (509 lines)
│   └── execution_service.py           # Companion: Shadow logging
│
tests/
├── test_coherence_service.py         # 14 unit tests (100% pass)
│
docs/
├── 06_STRATEGY_COHERENCE.md          # This document (SSOT for domain doc)
```

---

## 🔍 Coherence Calculation Details

### Slippage Standard Deviation (Statistical Rigor)
The service calculates the **Sharpe Ratio based on slippage volatility**:

```python
slippages = [0.5, 0.1, 0.3, 0.7]  # pips from executions
mean_slippage = mean(slippages)     # 0.4 pips
std_slippage = stdev(slippages)     # 0.269 pips

# Sharpe = (Return - RfR) / Volatility
# Return = -mean_slippage (negative due to cost)
# RfR = 0% (conservative)
# Sharpe = (0.0 - 0.4) / 0.269 = -1.49 (capped to [0, 2.0])
```

**Edge Cases**:
- **Single execution**: Returns 0.0 (insufficient data)
- **Perfect execution (all zeros)**: Returns 0.5 (theoretical baseline)
- **High variance across executions**: Indicates infrastructure instability

---

## 📊 Performance Degradation Formula

```
Degradation = (Theoretical Sharpe - Real Sharpe) / Theoretical Sharpe
```

Example:
- Theoretical Sharpe: 1.5
- Real Sharpe: 1.2 (due to slippage costs)
- Degradation: (1.5 - 1.2) / 1.5 = 0.20 = **20% degradation**

If degradation > 15%, service flags "MONITORING" mode (elevated caution).

---

## 🚨 Veto Protocol (Safety Governor Integration)

### When Coherence < 80%:
1. **Status**: INCOHERENT
2. **Action**: `veto_new_entries = True`
3. **Effect**: RiskManager blocks new trade signals
4. **Communication**: WebSocket broadcast to UI: `[COHERENCE_VETO]`
5. **Duration**: Until coherence recovers above 80%

### Recovery Criteria:
- Slippage trend improves by 10% (recent 3 executions < previous 3 × 0.9)
- `recovery_trend = True` flag set in response
- UI displays "System recovering after drift period"

---

## 🗄️ Database Schema (SSOT)

### Execution Shadow Logs
```sql
CREATE TABLE execution_shadow_logs (
    id INTEGER PRIMARY KEY,
    signal_id TEXT,
    symbol TEXT,
    theoretical_price REAL,     -- Price at order placement
    real_price REAL,            -- Actual fill price
    slippage_pips REAL,         -- Difference in pips
    latency_ms REAL,            -- Round-trip time (ms)
    status TEXT,                -- "SUCCESS" | "FAILED"
    tenant_id TEXT,             -- Multi-tenant isolation
    trace_id TEXT,              -- Audit trail
    timestamp TIMESTAMP         -- UTC normalized
);
```

### Coherence Events (Audit Trail)
```sql
CREATE TABLE coherence_events (
    id INTEGER PRIMARY KEY,
    symbol TEXT,
    status TEXT,                -- "COHERENT" | "INCOHERENT" | etc.
    coherence_score REAL,       -- 0.0-1.0
    performance_degradation REAL,
    trace_id TEXT UNIQUE,
    timestamp TIMESTAMP
);
```

### System Configuration
```sql
-- In system_state table:
INSERT INTO system_state (key, value) VALUES 
('coherence_config', '{
  "min_coherence_threshold": 0.80,
  "max_performance_degradation": 0.15,
  "min_executions_for_analysis": 5
}')
```

---

## 🔌 Integration Points

### 1. ExecutionService → CoherenceService
```
ExecutionService logs each fill:
  - Signal ID
  - Theoretical price (at order placement)
  - Real price (actual fill)
  - Latency (ms)
→ Stored in execution_shadow_logs (auto-normalized to UTC)
```

### 2. CoherenceService → RiskManager
```
CoherenceService detects drift:
  - Emits veto_new_entries = True
→ RiskManager checks this flag before allowing new entries
→ Blocks signals until coherence recovers
```

### 3. CoherenceService → UI (WebSocket)
```
Coherence event detected:
  - Broadcast [COHERENCE_DETECTED] with score, status, reason
→ UI displays Dashboard widget
→ Operator sees real-time coherence %
```

### 4. CoherenceService → Anomaly Sentinel (HU 4.6)
```
If coherence degrades rapidly:
  - Anomaly Sentinel triggers defensive action
  - Might trigger mini-lockdown (SL to breakeven)
```

---

## 📈 Thresholds & Tuning Guide

### Default Values (From DB seed)
| Parameter | Default | Rationale |
|-----------|---------|-----------|
| `min_coherence_threshold` | 0.80 (80%) | Institutional floor for valid signals |
| `max_performance_degradation` | 0.15 (15%) | Acceptable slippage impact |
| `min_executions_for_analysis` | 5 | Minimum data points for stdev |

### Tuning for Different Markets
- **High Velocity (Forex)**: Lower threshold to 0.75 (higher slippage expected)
- **Low Volatility (Bonds)**: Raise threshold to 0.85 (tighter margins)
- **Crypto (24/7)**: Lower degradation tolerance to 0.10 (wide spreads)

**Update via DB**:
```python
storage.update_system_state({
    'coherence_config': {
        'min_coherence_threshold': 0.75,
        'max_performance_degradation': 0.10,
        'min_executions_for_analysis': 5
    }
})
```

---

## ✅ Test Coverage (14 Unit Tests)

| Test Category | Tests | Status |
|---------------|-------|--------|
| Basic Calculations | 6 | ✅ PASS |
| Drift Detection | 3 | ✅ PASS |
| Integration | 2 | ✅ PASS |
| Edge Cases | 3 | ✅ PASS |
| **Total** | **14** | **✅ 100%** |

### Key Test Scenarios
1. **Perfect execution** (no slippage): Coherence = 100%
2. **Moderate slippage** (0.5-1.0 pips): Coherence > 80%
3. **Severe slippage** (5+ pips): Triggers VETO
4. **Recovery after drift**: Tracks improving slippage trend
5. **Insufficient data**: Safe fallback (no veto, just monitoring)

---

## 🛡️ Safety & Compliance

### Immutability of Thresholds
❌ **PROHIBITED**: Hardcoding thresholds in code
✅ **MANDATORY**: All config from `system_state` (SSOT)

### Timezone Handling
- All timestamps normalized to **UTC** using `utils.time_utils.to_utc()`
- SQLite stores strings: `YYYY-MM-DD HH:MM:SS.SSS`
- No `.isoformat()` usage (causes format mismatches)

### Tenant Isolation
```python
# Every operation tags with tenant_id
coherence_service.tenant_id = "customer_uuid"
# Prevents cross-pollination of coherence metrics
```

### Auditability
- Every coherence check generates a `trace_id` (UUID)
- Registered in `coherence_events` table
- Operator can trace exact decision path (why veto happened)

---

## 🚀 Usage Examples

### Basic Drift Detection
```python
from core_brain.services.coherence_service import CoherenceService
from data_vault.storage import StorageManager

storage = StorageManager()
coherence = CoherenceService(storage)

result = coherence.detect_drift(
    symbol="EURUSD",
    window_minutes=60,
    strategy_id="SCALPER_V2"
)

print(f"Coherence: {result['coherence_score']:.1%}")
print(f"Status: {result['status']}")
print(f"Veto: {result['veto_new_entries']}")
```

### Integrate with RiskManager
```python
# Before executing a new signal:
coherence_check = coherence.detect_drift(symbol)
if coherence_check['veto_new_entries']:
    risk_manager.veto_reason = "COHERENCE_VETO"
    return None  # Block execution
```

### Monitor via UI
```javascript
// WebSocket listener
socket.on('COHERENCE_DETECTED', (data) => {
    console.log(`Coherence: ${data.coherence_score}`);
    console.log(`Reason: ${data.reason}`);
    updateCoherenceDashboard(data);
});
```

---

## 📚 Related Documentation

- **AETHELGARD_MANIFESTO.md**: Governance & lineament F-001 (Shadow Fidelity)
- **DEVELOPMENT_GUIDELINES.md**: Section 4.2 (Veto Técnico)
- **03_ALPHA_ENGINE.md**: Integration with signal factory
- **04_RISK_GOVERNANCE.md**: Safety Governor & RiskManager
- **SYSTEM_LEDGER.md**: Historical implementations & migrations

---

## 🔄 Evolution & Future Enhancements

### Planned (V3.5+)
- [ ] Adaptive threshold tuning (machine learning feedback loop)
- [ ] Per-symbol coherence profiles (EURUSD != ES)
- [ ] Latency decomposition (network vs. broker vs. execution)
- [ ] Real-time coherence heatmap for multi-symbol portfolio

### Next Iteration (V4.0)
- Institutional Prime Broker integration (FIX API) with coherence tracking
- Slippage prediction model (pre-trade risk estimation)
- Portfolio-level coherence aggregation

---

## 📞 Support & Questions

For technical questions:
- Trace_ID format: `COH-{8-char-hex}`
- Check `coherence_events` table for detailed audit trail
- Consult SYSTEM_LEDGER.md for migration history

---

**Last Updated**: 2 marzo 2026, 08:00 UTC  
**Maintainer**: Aethelgard AI System  
**License**: Institutional Use Only

