"""
MT5 Wrapper - Acceso controlado a MetaTrader5

Este módulo centraliza el import de MetaTrader5 para mantener la arquitectura limpia.
Solo módulos en /connectors pueden importar directamente MetaTrader5.
"""

import MetaTrader5 as mt5

# Exportar la instancia para uso controlado
MT5 = mt5