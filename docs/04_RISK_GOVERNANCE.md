# Dominio 04: RISK_GOVERNANCE (Unidades R, Safety Governor, Veto)

## 🎯 Propósito
Garantizar la preservación del capital mediante una gestión de riesgo de nivel institucional, basada en la normalización universal de activos y la soberanía de intervención humana.

## 🚀 Componentes Críticos
*   **Universal Risk Manager**: Motor de cálculo basado en Unidades R que garantiza un riesgo constante en USD independientemente del activo.
*   **Sovereignty Gateway**: Matriz de permisos que define la autonomía del sistema por componente o mercado.
*   **Anomaly Sentinel**: Monitor de "Cisnes Negros" que activa protocolos de defensa ante eventos de baja probabilidad.
*   **Circuit Breakers**: Bloqueos automáticos por drawdown o fallos consecutivos.

## 📐 Filosofía de Cálculo: Unidades R
Aethelgard no opera instrumentos, sino **Volatilidad Normalizada**. 
*   **Fórmula**: `Lots = Risk_USD / (SL_Dist * Contract_Size)`
*   **Aritmética**: Uso obligatorio de `Decimal` para precisión financiera.
*   **Normalización**: Tabla `asset_profiles` como fuente única de verdad para tick sizes y contract sizes.

## 🖥️ UI/UX REPRESENTATION
*   **Master Veto Panel**: Consola de control con toggles de seguridad institucional para habilitar/deshabilitar autonomía por mercado.
*   **Exposure Heatmap**: Dashboard visual que muestra el riesgo agregado del portafolio y la proximidad al Hard Drawdown.
*   **Sentient Thought Console**: Feed de pensamientos con tags `[ANOMALY_DETECTED]` y sugerencias proactivas de intervención.

## 📈 Roadmap del Dominio
1.  Implementación del Sovereignty Gateway Manager.
2.  Despliegue de Drawdown Monitors multi-tenant.
3.  Integración del Anomaly Sentinel (Antifragility Engine).
