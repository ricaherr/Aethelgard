# Scripts de Utilidades

Herramientas recurrentes para testing, setup, monitoreo y mantenimiento del sistema.

## Setup y Configuración
- `setup_mt5_demo.py` - Configuración interactiva de cuenta demo MT5

## Testing y Validación
- `test_mt5_system.py` - Prueba completa de integración MT5
- `test_system_integration.py` - Validación de DB, credenciales y auto-provisioning
- `verify_trading_flow.py` - Verifica flujo completo: Signal → Risk → Execution
- `demo_live_trade.py` - Ejecuta trade demo en vivo
- `simulate_trades.py` - Simula trades para poblar histórico

## Monitoreo y Análisis
- `check_system.py` - Verifica salud del sistema
- `check_duplicates.py` - Analiza duplicados en DB
- `clean_duplicates.py` - Limpia señales duplicadas

## Ejemplos
- `example_traceability.py` - Ejemplo de uso de trazabilidad de señales

## Uso

```bash
# Desde el root del proyecto
py scripts/utilities/nombre_del_script.py
```

## 📝 Notas

Estos scripts se pueden ejecutar múltiples veces sin afectar datos (excepto clean_duplicates.py - usar con precaución).
