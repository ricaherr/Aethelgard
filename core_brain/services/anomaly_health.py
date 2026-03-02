"""
Anomaly Health Status Calculator
Evalúa el estado de salud del sistema basado en historial de anomalías.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def calculate_anomaly_health_status(
    symbol: str,
    anomaly_history: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calcula el estado de salud del símbolo basado en historial de anomalías.
    
    Args:
        symbol: Instrumento
        anomaly_history: Lista de eventos de anomalía (dicts con 'timestamp', etc)
        
    Returns:
        Dict con métricas de salud (mode, stability, etc)
    """
    try:
        # Contar anomalías en últimas 5 velas (consecutivas = últimos 300s)
        now = datetime.now()
        recent_anomalies = []
        
        for e in anomaly_history:
            try:
                # Parse timestamp (puede ser datetime o string ISO)
                ts = e.get("timestamp")
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
                
                if (now - ts).total_seconds() < 300:
                    recent_anomalies.append(e)
            except (TypeError, ValueError):
                # Skip invalid timestamps
                continue
        
        # Determinar modo operativo basado en anomalías consecutivas
        anomaly_count = len(anomaly_history)
        consecutive_anomalies = len(recent_anomalies)
        
        mode = "NORMAL"
        stability = 1.0
        
        if consecutive_anomalies >= 3:
            mode = "DEGRADED"
            stability = 0.5
        elif consecutive_anomalies >= 2:
            mode = "CAUTION"
            stability = 0.75
        elif anomaly_count > 10:
            mode = "STRESSED"
            stability = 0.6
        
        return {
            "symbol": symbol,
            "mode": mode,
            "anomaly_count": anomaly_count,
            "consecutive_anomalies": consecutive_anomalies,
            "system_stability": stability,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"[HEALTH_CALCULATOR] Error: {e}")
        return {
            "symbol": symbol,
            "mode": "UNKNOWN",
            "anomaly_count": 0,
            "consecutive_anomalies": 0,
            "system_stability": 0.5,
        }
