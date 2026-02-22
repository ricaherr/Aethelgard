# AETHELGARD: 02 RISK CONTROL

## 🛡️ Gestión de Riesgo y Compliance Técnico
Guardia algorítmica y controles de exposición para la preservación de capital.

---

### ⚖️ Capas de Riesgo
- **Risk Per Trade**: Base de 1.0%, adaptativo por `EdgeTuner`.
- **Account Risk Limit**: Máximo 5% de riesgo total agregado en cuenta.
- **Symbol Limits**: Restricción de posiciones y lotaje máximo por instrumento.
- **Lockdown Mode**: Protocolo de seguridad por drawdown excesivo o pérdidas consecutivas.

---

### 📉 Fail-Safes Proactivos
- **Risk Sanity Check**: Gate de cordura aritmético pre-ejecución.
- **JPY/Metal Fix**: Triangulación real y cálculo dinámico de point value.
- **Circuit Breaker**: Bloqueo tras N fallos de cálculo consecutivos.

---

### 📐 Filosofía de Cálculo: Agnosticismo de Activos (Universal Trading Foundation)
A partir de la versión 2.5.0, Aethelgard adopta un modelo de Cálculo Universal basado en Unidades R. Se elimina la dependencia de pips/centavos en favor de una normalización vía `asset_profiles`. Esto garantiza que el riesgo sea constante ($) independientemente de la volatilidad o el tipo de instrumento (Forex, Crypto, Stocks), permitiendo una comparabilidad real entre estrategias mediante el Shadow Ranking.

#### 🔧 Infraestructura Agnóstica
- **SSOT: Tabla `asset_profiles`** (Persistencia: `data_vault/market_db.py`)
  - Normaliza: `symbol`, `tick_size`, `contract_size`, `lot_step`, `pip_value`, `commission_pct`
  - Ejemplo: EURUSD (100000 contract size) vs BTCUSD (1 contract size) → Cálculo idéntico en USD

- **Método `RiskManager.calculate_position_size(symbol, risk_amount_usd, stop_loss_dist)`**
  - **Entrada**: símbolo, riesgo en USD, distancia en precio bruto
  - **Fórmula**: `Lots = Risk_USD / (SL_Dist * Contract_Size)`
  - **Aritmética**: `Decimal` (IEEE 754 → Decimal para exactitud institucional)
  - **Redondeo**: `ROUND_DOWN` según `lot_step` del activo
  - **Output**: Lotaje final listo para ejecutar

- **Seguridad & Trazabilidad**
  - `AssetNotNormalizedError` si símbolo no normalizado → Trade bloqueado
  - Trace_ID único (ej: `NORM-0a9dfe65`) para auditoría completa
  - Logging: `[{NORM-XXX}] Calculating 0.2 lots for EURUSD | Risk: $100 | SL: 0.0050`

#### ✅ Validación Completada
- **Test Suite**: 289/289 tests pass (6/6 validaciones agnósticas)
- **Cobertura**: EURUSD, GBPUSD, USDJPY, GOLD, BTCUSD
- **Precisión**: Downward rounding validado en 0.303030 → 0.3

---

### 🛡️ Resilience Protocol
El `RiskManager` es la autoridad final. Ninguna orden puede ser despachada al mercado sin su sello de aprobación ("Approved"). En modo agnóstico, se rechaza toda orden que no esté normalizada en `asset_profiles`.
