"""
Anomaly Suggestions Generator (HU 4.6)
Genera sugerencias inteligentes basadas en la naturaleza de anomalías detectadas.
Módulo separado para mantener anomaly_service.py bajo límite de 500 líneas.
"""

from typing import Dict
from core_brain.services.anomaly_models import AnomalyEvent, AnomalyType


def generate_thought_console_suggestion(event: AnomalyEvent) -> Dict[str, str]:
    """
    Genera sugerencias inteligentes basadas en la naturaleza  de la anomalía.
    
    Args:
        event: Evento de anomalía
        
    Returns:
        Dict con sugerencia y severidad
    """
    suggestions = {
        AnomalyType.EXTREME_VOLATILITY: {
            "suggestion": (
                "Volatilidad extrema detectada (Z-Score > 3). Consideraciones: "
                "1) Reducir tamaño de posición; 2) Activar protecciones automáticas; "
                "3) Revisar noticias macro; 4) Preparar Lockdown si persiste."
            ),
            "severity": "HIGH",
            "action": "reduce_position_size"
        },
        AnomalyType.FLASH_CRASH: {
            "suggestion": (
                "ALERTA: Flash Crash detectado (caída > -2% en 1 vela). Acciones URGENTES: "
                "1) Cancelar órdenes pendientes; 2) Cerrar posiciones pérdidas si es necesario; "
                "3) Ajustar SL a Breakeven; 4) Monitorear el mercado continuamente."
            ),
            "severity": "CRITICAL",
            "action": "lockdown_immediate"
        },
        AnomalyType.VOLUME_SPIKE: {
            "suggestion": (
                "Spike de volumen anómalo detectado. Posible liquidación institucional o "
                "colapso de oferta/demanda. Recomendar: monitorear movimientos subsequentes."
            ),
            "severity": "MEDIUM",
            "action": "monitor"
        },
        AnomalyType.LIQUIDATION_CASCADE: {
            "suggestion": (
                "CRÍTICO: Cascada de liquidaciones en el mercado. Sistema activará "
                "Lockdown preventivo automáticamente. Modo de defensa activado."
            ),
            "severity": "CRITICAL",
            "action": "lockdown_cascade"
        },
    }
    
    return suggestions.get(event.anomaly_type, {
        "suggestion": f"Anomalía {event.anomaly_type.value} detectada. Revisar manualmente.",
        "severity": "MEDIUM",
        "action": "review"
    })
