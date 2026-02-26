# Dominio 05: UNIVERSAL_EXECUTION (EMS, Conectores FIX)

## 🎯 Propósito
Garantizar una ejecución de órdenes de alta fidelidad y baja latencia mediante una infraestructura de conectividad agnóstica y un control estricto del slippage.

## 🚀 Componentes Críticos
*   **Connectivity Orchestrator**: Gestión centralizada de sesiones y estados de conexión con múltiples brokers.
*   **High-Fidelity FIX Connector**: Capa de transporte basada en QuickFIX para ejecución directa con Prime Brokers.
*   **Adaptive Slippage Controller**: Monitor de desviación de ejecución que inyecta datos de latencia real en el motor de riesgo.
*   **Source Fidelity Guard**: Prohíbe el arbitraje de datos entre proveedores para garantizar la integridad operativa.

## 🔌 Conectores y Proveedores de Datos
Aethelgard utiliza un sistema de **fallback automático** para garantizar la disponibilidad de datos de mercado.

*   **Yahoo Finance**: Principal proveedor gratuito para Forex, Stocks y Commodities.
*   **CCXT**: Puente universal para más de 100 exchanges de Criptomonedas.
*   **Alpha Vantage / Twelve Data / Polygon**: Proveedores con API Key para alta frecuencia y datos institucionales.
*   **MetaTrader 5 (MT5)**: Conexión nativa de alto rendimiento para ejecución y datos de broker.

## 📟 Guía Técnica de Instalación (MT5)
1.  **Descarga**: Se recomienda usar la versión directa del broker (Pepperstone, IC Markets, XM).
2.  **Instalación**: Usar rutas por defecto y cerrar la terminal tras la instalación.
3.  **Configuración**: Ejecutar `python scripts/setup_mt5_demo.py` para vincular credenciales a la DB de Aethelgard.
4.  **Verificación**: `python scripts/test_mt5_system.py` para validar latencia y ejecución.

## 🖥️ UI/UX REPRESENTATION
*   **FIX Telemetry Terminal**: Visualizador en tiempo real de la latencia ida y vuelta (RTT) y estados del heartbeat FIX.
*   **Efficiency Badge**: Etiqueta visual en cada trade cerrado que indica el % de ejecución eficiente (Slippage vs Teórico).
*   **System Vital Signs Widget**: Medidores de salud técnica, carga de red y estado de los hilos de ejecución.

## 📈 Roadmap del Dominio
1.  Despliegue del núcleo QuickFIX.
2.  Implementación del Feedback Loop de infraestructura (The Pulse).
3.  Desarrollo de algoritmos de ejecución inteligente (Smart Routing).
