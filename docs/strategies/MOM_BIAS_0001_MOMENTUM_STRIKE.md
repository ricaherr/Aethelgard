# MOM_BIAS_0001: MOMENTUM STRIKE (Vela Elefante con Ubicación Geométrica)

**Estrategia**: S-0004 (Momentum)  
**Versión**: 1.0 (Refined Logic)  
**Fecha**: 2 de Marzo 2026  
**TRACE_ID**: DOC-STRAT-MOM-REFINED-2026  

---

## 🎯 Filosofía

MOM_BIAS_0001 captura el impulso inicial de una ruptura de zona de compresión (SMA20/SMA200) mediante una **Vela Elefante** con requisitos geométricos específicos. No es suficiente tamaño; debe validarse posicionamiento relativo a las medias y confluencia.

---

## 📐 1. Lógica de Ubicación: Filtro de Ignición

### Escenario Alcista (BULLISH IGNITION)

**Requisito Primario: Vela Elefante**
- Cierre DEBE estar **≥ 2% por encima** del:
  - **O** máximo de la consolidación previa (últimas 5 velas)
  - **O** SMA20 (abiertamente)

**Requisito Secundario: Confluencia de Medias**
- **SMA20 debe estar en "compresión"** respecto a SMA200:
  - Máximo 10-15 pips de separación
  - **O** SMA20 cruzando AL ALZA respecto a SMA200 (en vela actual o previa)
  
**Validación de Impulso**
- El cierre debe ocurrir en la mitad superior de la vela (bullish)
- Volumen relativo ≥ promedio de 20 velas anteriores (confirmación)

---

### Escenario Bajista (BEARISH IGNITION)

**Requisito Primario: Vela Elefante**
- Cierre DEBE estar **≤ 2% por debajo** del:
  - **O** mínimo de la consolidación previa (últimas 5 velas)
  - **O** SMA20 (abiertamente)

**Requisito Secundario: Confluencia de Medias**
- **SMA20 debe estar en "compresión"** respecto a SMA200:
  - Máximo 10-15 pips de separación
  - **O** SMA20 cruzando A LA BAJA respecto a SMA200 (en vela actual o previa)

**Validación de Impulso**
- El cierre debe ocurrir en la mitad inferior de la vela (bearish)
- Volumen relativo ≥ promedio de 20 velas anteriores (confirmación)

---

## 💰 2. Gestión de Riesgo: Protocolo de Apertura

### Stop Loss (SL) — Regla de ORO

$$\text{SL} = \text{OPEN de la Vela Elefante}$$

**Por qué OPEN y no LOW/HIGH:**
1. **Maximiza el lotaje**: Riesgo absoluto más pequeño → más volumen por el mismo % de capital
2. **Protege el Alpha inicial**: Si precio vuelca debajo del OPEN, la premisa de impulso se invalida
3. **Simplicidad operativa**: OPEN es inambiguo, no depende de precios extremos intra-vela

---

### Risk/Reward Estándar

| Parámetro | Valor |
|-----------|-------|
| **Risk per Trade** | 1% del capital |
| **Reward/Risk Ratio** | 2:1 a 3:1 |
| **Take Profit** | Entry + (Risk × Ratio) |

**Ejemplo (SELL Bearish Ignition):**
```
Entry (alerta):   1.0500 (SMA20 cruzando; vela cerca)
Open (SL):        1.0510 (máximo de vela elefante)
Risk:             10 pips
Target 1 (2:1):   1.0490
Target 2 (3:1):   1.0480
```

---

## 🔍 3. Criterios de Validación

### Checklist Pre-Entrada

- [ ] **SMA20 y SMA200** están dentro de 10-15 pips (O en cruce)
- [ ] **Vela actual** cierra 2%+ lejos del máximo/mínimo previo o SMA20
- [ ] **Volumen** ≥ promedio 20 velas
- [ ] **Dirección de cierre** coincide con impulso (bullish close para BUY, bearish para SELL)
- [ ] **Confluencia adicional** (optional): Rejection Tail en vela previa (Pilar Trifecta)

### Checklist de Stop Loss

- [ ] SL = OPEN de la vela actual (no negociable)
- [ ] Riesgo total ≤ 1% del capital
- [ ] Risk/Reward ≥ 2:1

---

## 📊 4. Integración Técnica

### Archivo de Implementación
- **Sensor**: `core_brain/sensors/candlestick_pattern_detector.py`
- **Método**: `detect_momentum_strike()`
- **Dependencias**:
  - SMA20 (proporcionado por `moving_average_sensor.py`)
  - SMA200 (proporcionado por `moving_average_sensor.py`)
  - OHLC de vela actual y previa

### Parámetros de Configuración (en `dynamic_params.json`)

```json
{
  "mom_bias_closure_threshold": 0.02,      // 2% cierre por encima/debajo
  "mom_bias_sma_compression_pips": 15,     // Max 15 pips entre SMA20/200
  "mom_bias_volume_multiplier": 1.0,       // Vol >= promedio 20d
  "mom_bias_risk_percent": 0.01            // 1% del capital
}
```

---

## 🎮 5. Ejemplo de Operación

### Escenario: EUR/USD, M5, Alcista

**Contexto:**
- SMA200 (H1, proyectada a M5): 1.0700
- SMA20 (M5): 1.0708 (+8 pips) → En compresión
- SMA20 cruzó al alza SMA200 hace 15 minutos

**Vela Actual (M5, 14:15 UTC):**
- Open:  1.0710
- High:  1.0745
- Low:   1.0705
- Close: 1.0742 (cierre bullish)
- Vol:   125K vs 110K promedio 20d ✓
- Cierre 34 pips arriba de SMA20 (2% ~ 35 pips en EUR/USD) ✓

**Decisión: ENTRADA LONG**
- Entry: 1.0745 (high + 1 pip)
- SL: 1.0710 (OPEN) = 35 pips
- Risk: 1% capital → Lotaje = 1% / 35 pips
- TP (2:1): 1.0815

---

## 📈 6. Affinity Score (Multi-Instrumento)

MOM_BIAS_0001 es menos selectivo que Trifecta (acepta más pares). Scores indicativos:

| Instrumento | Affinity | Razón |
|-------------|----------|-------|
| EUR/USD | 0.92 | Alta compression, moving averages claras |
| GBP/USD | 0.85 | Buena estructura, volatilidad media |
| USD/JPY | 0.78 | Spreads más altos, movimientos menos fluidos |
| EUR/GBP | 0.72 | Correlación interna, consolidaciones frecuentes |
| Crude Oil (WTI) | 0.65 | Volumen asimétrico, correlaciones macro |
| S&P 500 Fut | 0.70 | Impulsos claros en NY, confusión pre-mercado |

---

## 🚨 7. Restricciones y Lockdown

**Modo Lockdown Activado Si:**
1. 3 pérdidas consecutivas en la estrategia
2. 2 violaciones de SL (cierre por debajo/encima del OPEN)
3. Drawdown acumulado > 3% del capital diario

**Acción Lockdown:**
- Detener nuevas entradas por 2 horas
- Revalidar SMA20/SMA200 manualmente
- Revisar zona de consolidación en timeframe superior

---

## 📝 8. Notas de Implementación

- **TDD Obligatorio**: Crear `tests/core_brain/test_momentum_strike.py` antes de código
- **Inyección DI**: Sensor recibe `storage` y `moving_average_sensor` inyectados
- **Validaciones**: Todas las comparaciones de precio con 5 decimales (FOREX precision)
- **Logging**: TRACE_ID + timestamp en cada decisión clave
- **Persistent State**: Registrar en DB cada entrada/SL/TP para backtesting

---

## 🔄 9. Hilo de Feedback

1. Ejecutar operación
2. Registrar en `execution_log` (DB)
3. A 5, 10, 20 velas: Medir P&L y PnL/Risk
4. Actualizar `dynamic_params.json` si P&L promedio diverge de 2:1 objetivo
5. Re-entrenar threshold del 2% si WR cae < 55%

---

**Documento de Referencia**: AETHELGARD_MANIFESTO.md (Sección: Estrategias)  
**Última Validación**: Antes de integración en MainOrchestrator  
**Estado**: 🚀 READY FOR IMPLEMENTATION
