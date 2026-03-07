# SHADOW Mode: Análisis Crítico y Plan de Remediación

## 🎯 Estado Actual: CATCH-22 Arquitectónico

### El Problema
Las estrategias en SHADOW están **bloqueadas completamente** de ejecución:

**Flujo Actual (INCORRECTO):**
```
Strategy starts → SHADOW mode
                  ↓
      CircuitBreaker.is_strategy_blocked_for_trading()
                  ↓
              execution_mode != 'LIVE' → True (BLOQUEADA)
                  ↓
      Executor rechaza signal
                  ↓
      NO trades → NO métricas → NO promoción
                  ↓
              Trapped in SHADOW forever ❌
```

### Root Cause
**Archivo**: [core_brain/circuit_breaker.py (línea 271)](core_brain/circuit_breaker.py#L271)
```python
def is_strategy_blocked_for_trading(self, strategy_id: str) -> bool:
    execution_mode = ranking.get('execution_mode')
    return execution_mode != 'LIVE'  # ← BLOQUEA SHADOW Y QUARANTINE
```

Esta lógica es **binaria y correcta a nivel de CircuitBreaker**, pero el problema upstream es que **Executor no tiene una vía para ejecutar SHADOW en modo paper**.

---

## ✅ Solución Arquitectónica (Según ROADMAP)

### Diseño Correcto: Hybrid Execution Routing
```
Strategy in SHADOW
      ↓
Executor.execute_signal(signal)
      ↓
[CAMBIO NECESARIO] ¿Permitir SHADOW pero con routing especial?
      ↓
IF execution_mode == 'SHADOW':
    - Use ConnectorType.PAPER (INTERNAL)
    - Use account_type='DEMO'
    - Record trade with execution_mode='SHADOW'
    - Accumulate metrics for strategy ranking
      ↓
ELSE (LIVE):
    - Use real connector (MT5/NT/etc)
    - Use account_type='REAL'
    - Execute with RiskManager checks
      ↓
Result: SHADOW can generate 50+ trades → Metrics → Promotion ✅
```

### El Requisito del ROADMAP (FASE D)
Línea 18 del ROADMAP:
> **Routing Executor**: Si `strategy.execution_mode` = SHADOW → use INTERNAL provider + DEMO account

**Estado FASE D**: ✅ Completada (Infraestructura)
- ✅ Tabla `trades` con columna `execution_mode`
- ✅ TradesMixin.get_trades(execution_mode='SHADOW')
- ❌ **MISSING**: Executor logic para detectar SHADOW y rutear a PAPER

---

## 🔧 Cambios Necesarios para Habilitar SHADOW

### 1. Modificar CircuitBreakerGate (Permisivo)
**Archivo**: [core_brain/services/circuit_breaker_gate.py](core_brain/services/circuit_breaker_gate.py)

**Cambio**:
```python
# ANTES (línea 87):
is_blocked = self.circuit_breaker.is_strategy_blocked_for_trading(strategy_id)
if is_blocked:
    return (False, "CIRCUIT_BREAKER_BLOCKED")

# DESPUÉS: Permitir SHADOW pero marcar que necesita routing PAPER
if is_blocked:
    # Get execution mode to differentiate between SHADOW vs QUARANTINE
    ranking = self.storage.get_strategy_ranking(strategy_id)
    execution_mode = ranking.get('execution_mode') if ranking else None
    
    if execution_mode == 'SHADOW':
        # Allow SHADOW: signal.connector_type será reasignado a PAPER 
        logger.debug(f"[CIRCUIT_BREAKER] Strategy {strategy_id} in SHADOW: will route to PAPER")
        return (True, None)  # ← Permitir
    else:
        # QUARANTINE or unknown: block
        return (False, "CIRCUIT_BREAKER_BLOCKED")
```

### 2. Modificar OrderExecutor (Routing Hybrid)
**Archivo**: [core_brain/executor.py](core_brain/executor.py#L180-250)

**Cambio**:
```python
# DESPUÉS del check de CircuitBreaker (línea ~200):
# If strategy is in SHADOW, override connector to PAPER
if strategy_id:
    ranking = self.storage.get_strategy_ranking(strategy_id)
    if ranking and ranking.get('execution_mode') == 'SHADOW':
        signal.connector_type = ConnectorType.PAPER  # Force PAPER routing
        signal.metadata['shadow_mode'] = True
        logger.debug(f"[SHADOW ROUTING] {strategy_id} redirected to PAPER connector")
```

### 3. Modificar TradeClosureListener (Métadata)
**Archivo**: [core_brain/trade_closure_listener.py](core_brain/trade_closure_listener.py)

**Cambio**: Asegurar que `save_trade_result()` registra correctamente execution_mode:
```python
# ANTES:
self.storage.save_trade_result(
    strategy_id=strategy_id,
    trade_data=trade_data
)

# DESPUÉS:
execution_mode = 'SHADOW' if signal_metadata.get('shadow_mode') else 'LIVE'
self.storage.save_trade_result(
    strategy_id=strategy_id,
    trade_data=trade_data,
    execution_mode=execution_mode  # ← Explícitamente SHADOW
)
```

### 4. Habilitar Métrica Recalculadora (StrategyRanker)
**Archivo**: [core_brain/strategy_ranker.py](core_brain/strategy_ranker.py)

**Cambio**: La línea 104-160 `_evaluate_shadow()` debe calcular métricas desde trades reales:
```python
def _evaluate_shadow(self, strategy_id: str, ranking: Dict) -> Dict[str, Any]:
    # ANTES: Lee valores DB sin actualizar
    profit_factor = ranking.get('profit_factor', 0.0)
    win_rate = ranking.get('win_rate', 0.0)
    
    # DESPUÉS: Recalcula desde trades SHADOW
    shadow_trades = self.storage.get_trades(execution_mode='SHADOW', strategy_id=strategy_id)
    
    if shadow_trades:
        profit_factor = self._calculate_profit_factor(shadow_trades)
        win_rate = self._calculate_win_rate(shadow_trades)
        completed_last_50 = len([t for t in shadow_trades[-50:]])
        
        # Actualizar DB
        self.storage.update_strategy_ranking(
            strategy_id=strategy_id,
            profit_factor=profit_factor,
            win_rate=win_rate,
            completed_last_50=completed_last_50
        )
    
    # RESTO: Lógica de promoción LIVE
    meets_profit_factor = profit_factor > 1.5
    meets_win_rate = win_rate > 0.50
    meets_trade_count = completed_last_50 >= 50
    
    if meets_trade_count and meets_profit_factor and meets_win_rate:
        # PROMOTE to LIVE
```

---

## 📊 Impacto de los Cambios

### Base de Datos
**Antes**:
```sql
SELECT * FROM strategy_ranking;
-- 6 strategies en SHADOW
-- profit_factor: 0.0, win_rate: 0.0, completed_last_50: 0
```

**Después** (después de 3-5 días con mercados abiertos):
```sql
SELECT * FROM strategy_ranking;
-- 6 strategies: Mix de SHADOW + LIVE
-- profit_factor: 1.2-2.5, win_rate: 45%-65%, completed_last_50: 50-200+
```

### Trades Table
**Antes**: Vacía
```sql
SELECT COUNT(*), execution_mode FROM trades GROUP BY execution_mode;
-- (0 rows)
```

**Después**:
```sql
SELECT COUNT(*), execution_mode FROM trades GROUP BY execution_mode;
-- 250 SHADOW
-- 0 LIVE (until promotion)
```

---

## 🧪 Validación Post-Cambios

### Test 1: SHADOW Execution
```python
def test_shadow_strategy_executes_in_paper():
    # 1. Set strategy to SHADOW
    # 2. Send signal
    # 3. Verify: ConnectorType changed to PAPER
    # 4. Verify: Trade recorded with execution_mode='SHADOW'
```

### Test 2: Automatic Promotion
```python
def test_shadow_promotion_to_live():
    # 1. Accumulate 60+ SHADOW trades
    # 2. Ensure PF > 1.5 and WR > 50%
    # 3. Run StrategyRanker.evaluate_all_strategies()
    # 4. Verify: execution_mode changed from SHADOW → LIVE
```

### Test 3: LIVE Execution Bypass
```python
def test_live_strategy_uses_real_connector():
    # 1. Promote strategy to LIVE
    # 2. Send signal
    # 3. Verify: ConnectorType is NOT overridden to PAPER
    # 4. Verify: Uses real MT5/NT connector
```

---

## 📋 Resumen de Implementación

| Archivo | Línea | Cambio | Prioridad |
|---------|-------|--------|-----------|
| circuit_breaker_gate.py | 87-95 | Permitir SHADOW (no QUARANTINE) | CRÍTICA |
| executor.py | 180-200 | Routing SHADOW → PAPER | CRÍTICA |
| trade_closure_listener.py | ~117 | Marcar trades como SHADOW | ALTA |
| strategy_ranker.py | 104-160 | Recalcular métricas desde trades | ALTA |
| tests/ | NEW | Test SHADOW execution + promotion | ALTA |

---

## ⏰ Estimación de Trabajo

- **Cambios Core**: 2-3 horas
- **Testing**: 2-3 horas  
- **Validación End-to-End**: 1-2 horas
- **Total**: 5-8 horas

---

## 🎯 Objetivo Mensurable

**Antes**: 6 estrategias TRAPPED en SHADOW (métricas=0)

**Después**: 
- ✅ Estrategias SHADOW ejecutando en PAPER
- ✅ Accumulating trades (visibles después de 3-5 días)
- ✅ Métricas actualizadas diariamente  
- ✅ Promoción automática a LIVE cuando PF>1.5 AND WR>50%
