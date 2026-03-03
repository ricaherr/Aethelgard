# S-0002: TRIFECTA CONVERGENCE (CONV_STRIKE_0001)

**Metadata**:
- **Strategy Class ID**: `CONV_STRIKE_0001`
- **Mnemonic**: `CONV_STRIKE_TRIFECTA`
- **Estado**: ✅ En Evaluación / Shadow Testing
- **Mercado Validación**: EUR/USD (Score 0.88)
- **Timeframe**: M5/M15 (Micro) + H1 (Macro)
- **Membresía**: Premium
- **Tipo**: Mean Reversion within Trend

## 1. El Concepto: "El Muro de Valor"
A diferencia de las acciones, el Forex es un mercado de reversión a la media. La Trifecta no busca solo una ruptura, sino la confirmación de que el "Smart Money" está defendiendo un nivel clave (SMA 20).

## 2. Los 4 Pilares del Protocolo Quanter

### Pilar Sensorial (Inputs)
| Indicador | Configuración | Propósito |
|-----------|---------------|-----------|
| **SMA 200** | H1 | Define ubicación macro (Barato/Caro) |
| **SMA 20** | M5/M15 | Línea de batalla (Soporte dinámico) |
| **Price Action** | Velas Japonesas | Detección de "Cola de Piso" o "Vela Elefante" |

### Pilar de Régimen (Hábitat)
- **Régimen Requerido**: Tendencia Confirmada con Retroceso Saludable.
- **Validación**: Precio > SMA 200 (H1) para largos.
- **Filtro**: Se rechazan operaciones si el precio está "extendido" (muy lejos de la SMA 20) sin haber tocado la media.

### Pilar de Coherencia (Health Check)
- **Spread Máximo**: < 1.0 pip (Crucial para M5).
- **Asset Affinity Score**:
    - EUR/USD: 0.88 (Alta probabilidad)
    - USD/JPY: 0.75 (Media)
    - GBP/JPY: 0.45 (Baja - Veto por ruido)

### Pilar Multi-tenant (Gestión de Riesgo)
- **Riesgo por Trade**: 1% del capital (Unidades R).
- **Ratio Riesgo/Beneficio**: 1:2.5.

## 3. Lógica Operativa

### Entry Logic (El Gatillo)
1. **Tendencia**: Precio por encima de la SMA 200 en H1.
2. **Retroceso**: El precio retrocede y toca o perfora momentáneamente la SMA 20 en M5/M15.
3. **Señal**: Formación de una vela de reversión:
    - **Cola de Piso (Hammer)**: La mecha inferior es al menos el 50% del rango total de la vela.
    - **Vela Elefante**: Una vela de cuerpo grande que envuelve a la anterior tras tocar la media.
4. **Trigger**: Orden Buy Stop 1 pip por encima del máximo de la vela de señal.

### Exit Logic
- **Stop Loss**: 1 pip por debajo de la cola de la vela de entrada (Protección estructural).
- **Take Profit**: Objetivo fijo de 2.5R.
- **Gestión**: Mover a Breakeven al alcanzar 1R.

## 4. Matriz de Afinidad (Asset Scores)
El sistema utiliza estos scores para filtrar la ejecución en activos menos eficientes para esta estrategia.

| Activo | Score | Estado | Razón |
|--------|-------|--------|-------|
| **EUR/USD** | **0.88** | ✅ **PRIME** | Respeta SMA 20 tras expansiones. Liquidez máxima. |
| **USD/JPY** | 0.75 | ⚠️ MONITOR | Aceptable, pero propenso a mechas profundas. |
| **GBP/JPY** | 0.45 | ❌ VETO | Ruido excesivo, viola promedios sin reversión limpia. |

---
*Documento generado bajo operación ALPHA_TRIFECTA_S002.*