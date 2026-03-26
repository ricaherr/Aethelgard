"""
Paquete adaptive — Controladores de Adaptación Dinámica.

Contiene componentes de auto-ajuste que operan sobre instancias SHADOW/BACKTEST
para optimizar la exploración autónoma del sistema sin intervención humana.
"""
from core_brain.adaptive.threshold_controller import DynamicThresholdController

__all__ = ["DynamicThresholdController"]
