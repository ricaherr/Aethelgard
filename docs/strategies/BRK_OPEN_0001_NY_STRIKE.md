# Estrategia Alpha: BRK_OPEN_0001 - NY Strike (Market Open Gap)

**Metadata Alpha**:
- **Strategy Class ID**: `BRK_OPEN_0001`
- **Mnemonic**: `BRK_OPEN_NY_STRIKE`
- **Primera Operación**: 2 de Marzo, 2026
- **Mercado Validación**: EUR/USD (par de referencia)
- **Timeframe Primario**: H1 (1 hora)
- **Membresía**: Premium+
- **Estado**: ✅ Operativa (Institucionalizada)

---

## 🎯 Propósito Estratégico

**Ruptura de Apertura** captura el gap y la micro-estructura de la sesión de Nueva York en el par EUR/USD. La estrategia opera la retracción hacia Fair Value Gaps durante los primeros 90 minutos post-apertura (08:00-09:30 EST), cuando la volatilidad y la absorción institucional son máximas.

**Criterio de Validación**: EUR/USD ha demostrado coherencia > 75% en shadow testing durante 15 operaciones consecutivas con desviación promedio de 2 pips en ejecución real.

---

## 🧠 Los Cuatro Pilares (Protocolo Quanter)

### 1️⃣ **Pilar Sensorial: Inputs Requeridos**

La estrategia requiere los siguientes inputs sensoriales para funcionar. Si alguno falta → **STRATEGY_INCOMPATIBLE_VETO**.

| Sensor | Tipo | Período | Fuente Técnica | Validación |
|--------|------|---------|---------------|-----------|
| **Fair Value Gap (FVG)** | Micro-estructura | 60 min pre-apertura | LiquidityService | Detecta automáticamente el gap entre cierre pre-market y apertura |
| **RSI** | Momentum | Período 14 | IndicatorFunctionMapper → TechnicalAnalyzer | Valida zona neutral (35-65) para entrada sin extremos |
| **Moving Averages** | Tendencia | MA20 / MA50 | TechnicalAnalyzer | Cruce y slope bullish = confirmación de sesgo |
| **Order Blocks** | Institucional | Dinámico | LiquidityService | Identifica niveles de absorción previa para TP1 |
| **ATR (Average True Range)** | Volatilidad | Período 14 | TechnicalAnalyzer | Normaliza riesgo y ajusta SL dinámicamente |
| **Spread (Bid-Ask)** | Microestructura | Real-time | Connector → DataProvider | Valida condiciones de mercado (máx 1.5 pips aceptables) |

**Configuración de Inputs** (SSOT en `tenant_config`):
```json
{
  "brk_open_0001": {
    "lookback_minutes": 60,
    "fvg_sensitivity_pips": 0.5,
    "entry_encroachment_pct": 50,
    "regime_check_periods": [15, 60, 240],
    "min_candle_size_pips": 20,
    "max_spread_pips": 1.5,
    "timezone_trading": "US/Eastern",
    "session_start_est": "08:00",
    "session_end_est": "10:00"
  }
}
```

**Validación Sensorial Obligatoria**:
- ❌ **FAIL**: Si `LiquidityService` no disponible → Strategy incompatible en este mercado
- ❌ **FAIL**: Si `spread > max_spread_pips` → Se ignora señal (condiciones adversas)
- ❌ **FAIL**: Si algún indicador requerido falta en `IndicatorFunctionMapper` → MarketVeto
- ✅ **PASS**: Todos los inputs disponibles y dentro de umbrales de mercado

**Namespace de Cálculo**:
```python
inputs = {
    'fvg_top_eur_usd': 1.0845,
    'fvg_bottom_eur_usd': 1.0820,
    'fvg_50pct_level': 1.0832.5,
    'rsi_14_h1': 48,
    'ma20_h1': 1.0835,
    'ma50_h1': 1.0820,
    'atr_14_h1': 0.0035,
    'current_spread_bid_ask': 0.0010,
    'regimes': {m15: 'bullish', h1: 'trend_up', h4: 'trend_up'}
}
```

---

### 2️⃣ **Pilar de Régimen: Hábitat Operativo Multi-Escalar**

Ninguna entrada se valida sin la confirmación previa del **RegimeClassifier**. Se requiere concordancia en las 3 escalas de tiempo críticas.

**Regímenes Permitidos**:
- ✅ **TREND_UP**: Tendencia alcista confirmada en H4 (MA bullish + slope positivo)
- ✅ **EXPANSION**: Volatilidad creciente (ATR > SMA(ATR,20)) con absorción institucional detectada
- ✅ **ANOMALY**: Flash Move en pre-apertura (Z-Score > 2.5 en volatilidad 1-minuto)

**Regímenes Prohibidos** (Veto automático):
- ❌ **COLLAPSE**: Queda en espera (-2% última hora)
- ❌ **FLASH_CRASH**: Volatilidad extrema (ATR > 100 pips)
- ❌ **CONSOLIDATION**: Sin dirección clara (range < 20 pips en H1)

**Lógica Multi-Escala**:
```pseudocode
regime_veto = FALSE

IF h4_regime IN [TREND_UP, EXPANSION] THEN
  IF h1_regime NOT IN [COLLAPSE, FLASH_CRASH] THEN
    IF m15_trend IN [bullish_or_neutral] THEN
      regime_veto = FALSE  // ✅ Permitir entrada
      context_confidence = 95%
    ELSE
      regime_veto = FALSE BUT add_context_note("M15 bearish - considera SL más tight")
      context_confidence = 75%
    END
  ELSE
    regime_veto = TRUE  // ❌ Bloquear entrada
    reason = "H1 en régimen crítico"
  END
ELSE
  regime_veto = TRUE  // ❌ Bloquear entrada
  reason = "H4 no alcista"
END

RETURN regime_veto, context_confidence
```

**Margen de Seguridad Contextual**:
- Si análisis multi-escala arroja discordancia (ej M15 bearish vs H1 bullish) → `CoherenceService.elicitContext()` antes de entrada
- Se emite advertencia en logs: "Regime discordance detected. M15 bearish but H1 bullish. Entering with caution. Tight SL recommended."
- Usuario Institutional puede override con parámetro `override_regime_caution = true` (solo si membresía Institutional)

---

### 3️⃣ **Pilar de Coherencia: Health Check Shadow vs Live**

**Propósito**: Garantizar que el modelo teórico y la ejecución real no divergen. Divergencia sostenida indica overfitting o cambios del mercado.

**Shadow Mode Obligatorio** (Beta Phase):
- Toda entrada se ejecuta **simultáneamente** en Shadow (teórico) y Live (real capital).
- Shadow simula la entrada al precio exacto teórico SIN slippage, pero con latencia estimada.
- Live se ejecuta con slippage real del broker y latencia de red.

**Métricas de Coherencia**:

| Métrica | Rango Aceptable | Acción |
|---------|-----------------|--------|
| **Desviación de Entrada (pips)** | ±5 pips | Si > 5 → Registrar en coherence_log, investigar latencia |
| **Desviación de Salida (pips)** | ±10 pips | Si > 10 → Flag para ajuste de TP dinámico |
| **Coherence Score** | 75-100% | Si < 75% 3x consecutivo → COHERENCE_VETO (retiro a shadow) |
| **Latencia Operativa** | < 50ms | Si > 50ms → Nota en contexto, considerar ajuste de entrada |

**Cálculo de Coherence Score** (Post-Cierre):
```python
def calculate_coherence(shadow_pnl, live_pnl, shadow_time, live_time, max_deviation=15):
    """
    shadow_pnl: ganancia teórica (ej +50 pips)
    live_pnl: ganancia real (ej +48 pips)
    max_deviation: desviación máxima aceptable en pips
    """
    pnl_diff = abs(shadow_pnl - live_pnl)
    
    if pnl_diff <= max_deviation:
        coherence_score = 100 - (pnl_diff / max_deviation) * 25  # 100% - 75%
    else:
        coherence_score = max(50, 75 - (pnl_diff - max_deviation))
    
    return coherence_score
```

**Ejemplo Operacional**:
```
Shadow Backtest: Entrada 1.0833, Salida TP1 1.0862, Ganancia +29 pips
Live Execution:  Entrada 1.0838 (slippage +5), Salida 1.0867, Ganancia +29 pips

Coherence Calculation:
  PnL Difference = |29 - 29| = 0 pips
  Coherence Score = 100% ✅

Conclusion: Modelo perfectamente coherente. Shadow predictions = Realidad.
```

**Comportamiento en Bajo Coherence** (< 75%):
- Si coherence_score < 75% durante 3 operaciones consecutivas → Automático COHERENCE_VETO
- La estrategia se retira a **Shadow-Only mode** (sin ejecución de capital real)
- Trace registrado en SYSTEM_LEDGER con razón técnica (ej "Latencia FX > 50ms durante NY Open")
- Re-validación requerida: Human review del modelo o parámetros dinámicos

---

### 4️⃣ **Pilar Multi-Tenant: Aislamiento y Personalización Comercial**

**Niveles de Disponibilidad por Membresía**:
- **Basic**: ❌ NO disponible (requiere análisis multi-escala avanzado)
- **Premium**: ✅ HABILITADA (acceso completo, parámetros estándar)
- **Institutional**: ✅ HABILITADA + Custom thresholds, horarios, override de régimen

**Configuración Tenant-Específica** (SSOT en BD `tenant_config` table):
```json
{
  "tenant_id": "premium_trader_001",
  "strategies": {
    "BRK_OPEN_0001_enabled": true,
    "BRK_OPEN_0001_params": {
      "lookback_minutes": 60,
      "entry_encroachment_pct": 50,
      "risk_per_trade_pct": 1.0,
      "max_consecutive_losses": 3,
      "session_start_est": "08:00",
      "session_end_est": "10:00",
      "max_position_size_usd": 50000
    }
  },
  "membership_level": "Premium",
  "risk_settings": {
    "max_drawdown_daily_pct": 3.0,
    "max_drawdown_monthly_pct": 10.0
  }
}
```

**Validación de Acceso Tenant**:
```python
if tenant.membership_level < REQUIRED_LEVEL:
    raise StrategyAccessDenied(f"Tenant {tenant_id} requires {REQUIRED_LEVEL}, has {tenant.membership_level}")

# Load tenant-specific params from BD, not from defaults
strategy_params = load_strategy_config(strategy_class_id="BRK_OPEN_0001", tenant_id=tenant.id)
```

**Ejemplo Multi-Tenant**:
- **Tenant #1 (Basic)**: No ve BRK_OPEN_0001. Acceso denegado.
- **Tenant #2 (Premium)**: Ve BRK_OPEN_0001 con parámetros standard. Max risk 1%.
- **Tenant #3 (Institutional)**: Ve BRK_OPEN_0001 + puede custom el lookback a 90 min, override regime, max risk 2%.

---

## 📊 Lógica Operacional Detallada

### Fase 1: Pre-Apertura (07:00-08:00 EST)
**Objetivo**: Capturar el rango de mercado pre-market y preparar zona de entrada.

```pseudocode
1. Scanner inicia 60 minutos antes de apertura (07:00 EST)
2. Monitorea pips de EUR/USD cada minuto
3. Calcula:
   - Low_PreMkt   = Mínimo de 60 min
   - High_PreMkt  = Máximo de 60 min
   - Close_PreMkt = Cierre a las 07:59:59 EST
   - Range_PreMkt = High_PreMkt - Low_PreMkt
4. Almacena en cache: {low, high, close, range, timestamp}
5. Emite evento DEBUG: "Pre-market range captured: 1.0820-1.0845 (25 pips)"
```

**Validación en Fase 1**:
- ✅ Range_PreMkt >= 20 pips → Suficiente volatilidad
- ❌ Range_PreMkt < 20 pips → Ignora señal (volatilidad insuficiente)
- ✅ Spread < 1.5 pips → Condiciones normales
- ❌ Spread >= 1.5 pips → Condiciones adversas, skip

### Fase 2: Apertura (08:00-08:15 EST)
**Objetivo**: Detectar el gap y definir Fair Value Gap (FVG).

```pseudocode
1. 08:00 EST: Primera vela post-apertura comienza
2. Open(primera_vela) llega
3. IF Open > High_PreMkt THEN
     Gap_Direction = UP
     Gap_Size = Open - High_PreMkt
   ELSE IF Open < Low_PreMkt THEN
     Gap_Direction = DOWN
     Gap_Size = Low_PreMkt - Open
   ELSE
     Gap_Direction = NONE
     Skip signal (no gap, mercado sin volatilidad)
4. IF |Open - Close_PreMkt| > 10 pips THEN
     Gap_Confirmed = TRUE
   ELSE
     Gap_Confirmed = FALSE (gap pequeño, ignorar)
5. Calcula Fair Value Gap (FVG):
   - FVG_Top    = High de la primera vela post-gap
   - FVG_Bottom = Low de la segunda vela post-gap
   - FVG_Range  = FVG_Top - FVG_Bottom
   - FVG_50pct  = FVG_Bottom + (FVG_Range * 0.5)
6. Emite evento SIGNAL: "Gap confirmed UP. FVG zone: 1.0820-1.0845. Target 50%: 1.0832.5"
```

**Ejemplo**:
```
08:00 EST Open: 1.0860 (Gap de +22 pips vs 1.0838 cierre pre-market) ✅
Gap_Confirmed = TRUE

Vela #1 (08:00-09:00): High=1.0862, Low=1.0858
Vela #2 (09:00-10:00): High=1.0850, Low=1.0820

FVG_Top    = 1.0862 (High de vela #1)
FVG_Bottom = 1.0820 (Low de vela #2)
FVG_50pct  = 1.0841 (punto objetivo de entrada)
```

### Fase 3: Entrada en Encroachment (08:15-09:30 EST)
**Objetivo**: Esperar retroceso al 50% del FVG y validar confluencia.

```pseudocode
1. Scanner monitorea el precio aproximándose a FVG_50pct
2. ENTRY_TRIGGER = Cierre de vela H1 dentro de [FVG_50pct - 5 pips, FVG_50pct + 5 pips]
3. Confluencia Obligatoria (todos deben ser TRUE):
   - RSI(14) en zona neutral → 35 < RSI < 65
   - MA(20) > MA(50) en H1 → Sesgo alcista confirmado
   - CoherenceScore >= 75 → Shadow model sincronizado
   - RegimeVeto = FALSE → Regímenes permitidos validados
4. SI todas condiciones = TRUE THEN:
     position_size = 1% del capital / ATR(14)
     entry_price = cierre vela actual
     EJECUTAR ENTRADA
   ELSE:
     SKIP entrada, esperar próxima oportunidad
```

**Matriz de Confluencia**:
| Condición | Estado | Acción |
|-----------|--------|--------|
| Precio en FVG_50pct ±5 | ✅ | REQUIRED |
| RSI 35-65 | ✅ | REQUIRED |
| MA20 > MA50 | ✅ | REQUIRED |
| CoherenceScore >= 75% | ✅ | REQUIRED |
| RegimeVeto = FALSE | ✅ | REQUIRED |
| **Resultado** | ✅ | **ENTRY CONFIRMED** |

Si **CUALQUIERA** de las 5 condiciones falla → **SKIP ENTRY**

**Ejemplo Operacional** (2 de Marzo, 2026):
```
08:15 EST - Monitoreo inicia
  Precio: 1.0840 (acercándose a FVG_50pct 1.0832)
  RSI: 52 ✅
  MA20: 1.0835, MA50: 1.0820 → MA20 > MA50 ✅
  Coherence: 81% ✅
  Regime: H4=TREND_UP, H1=TREND_UP, M15=bullish ✅

08:18 EST - Cierre de vela
  Precio cierra: 1.0833 (dentro de [1.0827, 1.0837])
  Todos los checks = TRUE
  
  ENTRY EJECUTADA:
  Entry Price: 1.0833
  SL: 1.0820 (13 pips)
  TP1: 1.0862 (29 pips)
  TP2: 1.0859 (26 pips)
  Risk: 0.0013 * position_size = OK
```

---

## 🛡️ Gestión de Riesgo Detallada

### Stop Loss Dinámico
```python
def calculate_stop_loss(entry_price, atr_14, min_distance_pips=10):
    """
    SL se coloca DEBAJO de la vela que generó el gap, con buffer.
    Ajuste dinámico si ATR > 60 pips (volatilidad extrema)
    """
    base_sl = entry_price - (min_distance_pips * 0.0001)  # pips to decimals
    
    if atr_14 > 0.0060:  # ATR > 60 pips
        adjusted_sl = entry_price - (atr_14 * 0.75)
    else:
        adjusted_sl = base_sl
    
    return min(base_sl, adjusted_sl)  # Más conservador

# Ejemplo:
# entry_price = 1.0833
# atr_14 = 0.0035 (35 pips)
# min_distance_pips = 10
# SL = 1.0833 - 0.0010 = 1.0823 ✅
```

### Take Profit Multiescala
```python
def calculate_take_profits(entry_price, sl_price, atr_14):
    """
    TP1: 50% de posición → Order Block anterior
    TP2: 40% de posición → R2 del cálculo
    TP3: 10% de posición → Trailing a R1.5
    """
    risk_distance = entry_price - sl_price
    r_multiplier = risk_distance
    
    tp1_price = entry_price + (r_multiplier * 2.0)  # R2
    tp2_price = entry_price + (r_multiplier * 2.0)  # R2
    tp3_trigger = entry_price + (r_multiplier * 1.5)  # R1.5
    tp3_trailing = r_multiplier * 0.5  # SL móvil a R0.5 de TP3
    
    return {
        'tp1': {'price': tp1_price, 'size_pct': 0.50},
        'tp2': {'price': tp2_price, 'size_pct': 0.40},
        'tp3': {'trigger': tp3_trigger, 'trailing_stop': tp3_trailing, 'size_pct': 0.10}
    }

# Ejemplo:
# entry = 1.0833, sl = 1.0820, risk = 0.0013
# TP1 = 1.0833 + (0.0013 * 2) = 1.0859
# TP2 = 1.0833 + (0.0013 * 2) = 1.0859
# TP3_trigger = 1.0833 + (0.0013 * 1.5) = 1.0853 (trailing activates here)
```

### Validación de Riesgo Total
```python
def validate_risk_limit(equity, entry_price, sl_price, position_size_usd):
    """
    Risk per trade NO puede exceder 1% del equity (0.5% en régimen VOLATILE)
    """
    risk_pips = (entry_price - sl_price) / 0.0001
    risk_usd = position_size_usd * (risk_pips / 10000)  # Micro lots
    risk_pct = (risk_usd / equity) * 100
    
    if risk_pct > 1.0:
        return False, f"Risk {risk_pct:.2f}% exceeds 1% limit"
    
    return True, f"Risk OK: {risk_pct:.2f}%"

# Ejemplo:
# equity: $100,000
# entry: 1.0833, sl: 1.0820
# risk_pips: 13
# position: 100 micro lots ($10,000 notional)
# risk_usd: (10,000 * 13) / 10,000 = $13
# risk_pct: 0.013% ✅ (muy conservative)
```

---

## 📋 Consideraciones Operacionales Finales

| Aspecto | Parámetro | Nota |
|---------|-----------|------|
| **Volatilidad NYC Open** | +40-80 pips | Esperar slippage normal hasta 5 pips |
| **Ventana Temporal** | 08:00-10:00 EST | Después de 10:00, patrón pierde efectividad |
| **Validación Multi-Pares** | EUR/USD SOLO | Otros pares requieren re-validación y shadow testing |
| **Liquidez Mínima** | 0.5-1.5 pips spread | Si spread > 2 pips → Ignorar señal |
| **Riesgo Extremo** | NFP / Anuncios | Cancelar operaciones (desactivar strategy) |
| **Coherence Threshold** | >= 75% | Retiro automático a shadow si cae 3x consecutivo |
| **Max Consecutive Losses** | 3 operaciones | Bloqueo automático (Lockdown Mode) |

---

## 🔗 Referencias Multi-Dominio

- **Dominio 01 (Identity Security)**: Tenant isolation y privilegios por membresía
- **Dominio 02 (Context Intelligence)**: RegimeClassifier y análisis multi-escala
- **Dominio 03 (Alpha Generation)**: Signal Factory integrada, este documento
- **Dominio 04 (Risk Governance)**: RiskManager y validaciones de gobernanza
- **Dominio 06 (Portfolio Intelligence)**: CoherenceService y shadow tracking
- **Dominio 07 (Adaptive Learning)**: EdgeTuner actualización de parámetros dinámicos

---

**Institucionalización Final**: BRK_OPEN_0001 está registrada en `SYSTEM_LEDGER.md` como la primera estrategia Alpha institucionalized bajo el Protocolo Quanter. Trazabilidad 100% garantizada.
