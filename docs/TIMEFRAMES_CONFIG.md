# Configuración de Timeframes - Aethelgard

## Descripción

El archivo `config/config.json` permite configurar qué timeframes escaneará el sistema para cada instrumento habilitado. Esto permite al usuario:

- **Activar/Desactivar timeframes** según su estilo de trading
- **Reducir carga del sistema** desactivando timeframes no utilizados
- **Enfocarse en estrategias específicas** (scalping, swing, etc.)

## Configuración por Defecto

```json
"timeframes": [
  {"timeframe": "M1", "enabled": false},
  {"timeframe": "M5", "enabled": true},
  {"timeframe": "M15", "enabled": true},
  {"timeframe": "H1", "enabled": true},
  {"timeframe": "H4", "enabled": true},
  {"timeframe": "D1", "enabled": true}
]
```

## Timeframes Disponibles

| Timeframe | Descripción | Recomendado Para | Ventana Dedup |
|-----------|-------------|------------------|---------------|
| **M1** | 1 minuto | Scalping agresivo | 10 min |
| **M5** | 5 minutos | Scalping moderado | 20 min |
| **M15** | 15 minutos | Day trading | 45 min |
| **H1** | 1 hora | Day trading / Swing | 120 min |
| **H4** | 4 horas | Swing trading | 480 min |
| **D1** | Diario | Position trading | 1440 min |

## Casos de Uso

### Scalper Puro (Solo M1, M5)

```json
"timeframes": [
  {"timeframe": "M1", "enabled": true},
  {"timeframe": "M5", "enabled": true},
  {"timeframe": "M15", "enabled": false},
  {"timeframe": "H1", "enabled": false},
  {"timeframe": "H4", "enabled": false},
  {"timeframe": "D1", "enabled": false}
]
```

**Ventajas**:
- Menor carga de CPU
- Respuesta rápida a movimientos de precio
- Enfoque 100% en operativa intradiaria

### Swing Trader (H1, H4, D1)

```json
"timeframes": [
  {"timeframe": "M1", "enabled": false},
  {"timeframe": "M5", "enabled": false},
  {"timeframe": "M15", "enabled": false},
  {"timeframe": "H1", "enabled": true},
  {"timeframe": "H4", "enabled": true},
  {"timeframe": "D1", "enabled": true}
]
```

**Ventajas**:
- Menos ruido de mercado
- Análisis de tendencias más amplias
- Menor frecuencia de trades

### Operador Multi-Estrategia (Todos activos)

```json
"timeframes": [
  {"timeframe": "M1", "enabled": true},
  {"timeframe": "M5", "enabled": true},
  {"timeframe": "M15", "enabled": true},
  {"timeframe": "H1", "enabled": true},
  {"timeframe": "H4", "enabled": true},
  {"timeframe": "D1", "enabled": true}
]
```

**Ventajas**:
- Máxima cobertura de oportunidades
- Confirmación cross-timeframe
- Diversificación de estrategias

**Desventajas**:
- Mayor uso de CPU/RAM
- Mayor demanda al proveedor de datos
- Más señales a procesar

## Impacto en Rendimiento

### Cálculo de Carga

Para cada símbolo habilitado en `instruments.json`:

```
Total Combinaciones = N_símbolos × N_timeframes_activos
```

**Ejemplo**:
- 20 símbolos habilitados
- 5 timeframes activos
- **Total: 100 combinaciones a escanear**

### Recomendaciones de CPU

| Timeframes Activos | Símbolos | CPU Recomendada | RAM Mínima |
|-------------------|----------|-----------------|------------|
| 1-2 | 10-20 | 2 cores | 2 GB |
| 3-4 | 10-20 | 4 cores | 4 GB |
| 5-6 | 10-20 | 6 cores | 8 GB |
| 5-6 | 50+ | 8+ cores | 16 GB |

## Configuración de Modo de Escaneo

Además de timeframes, puedes ajustar el modo de escaneo en `config.json`:

```json
"scanner": {
  "scan_mode": "STANDARD",  // ECO, STANDARD, AGGRESSIVE
  "cpu_limit_pct": 80.0
}
```

### Modos Disponibles:

**ECO**: Conservador
- CPU límite: 50%
- Workers: 50% del base
- Sleep multiplicado: 2x
- **Uso**: PCs de bajo rendimiento o laptop con batería

**STANDARD**: Balanceado (recomendado)
- CPU límite: 80%
- Workers: 100% del base
- Sleep normal: 1x
- **Uso**: PCs de escritorio normales

**AGGRESSIVE**: Máximo rendimiento
- CPU límite: 95%
- Workers: 200% del base
- Sleep reducido: 0.5x
- **Uso**: Servidores dedicados o PCs de alta gama

## Cómo Modificar

1. Editar `config/config.json`
2. Cambiar `enabled` a `true` o `false` según necesidad
3. Reiniciar el sistema para aplicar cambios

```bash
# Reiniciar orquestador
python core_brain/main_orchestrator.py
```

## Verificación

Para verificar qué timeframes están activos:

```python
from core_brain.scanner import ScannerEngine

scanner = ScannerEngine(assets=["EURUSD"], data_provider=provider)
print(f"Timeframes activos: {scanner.active_timeframes}")
```

## Mejores Prácticas

1. **Empezar conservador**: Habilitar solo 2-3 timeframes inicialmente
2. **Monitorear CPU**: Ajustar según uso real del sistema
3. **Alinear con estrategia**: Scalper no necesita D1, swing trader no necesita M1
4. **Testear en demo**: Validar carga antes de producción
5. **Escalar gradualmente**: Agregar timeframes de uno en uno

## Troubleshooting

### Sistema muy lento
- Reducir número de timeframes activos
- Cambiar a modo ECO
- Reducir número de símbolos en `instruments.json`

### Pocas señales
- Habilitar más timeframes
- Verificar que símbolos estén habilitados en `instruments.json`
- Revisar logs del scanner

### Demasiadas señales
- Desactivar timeframes muy cortos (M1)
- Aumentar `min_score` en `instruments.json`
- Usar filtros por régimen de mercado
