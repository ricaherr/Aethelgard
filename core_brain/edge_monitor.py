"""
EDGE Monitor - Observabilidad Autónoma para Aethelgard
Monitorea inconsistencias entre módulos y genera informes de aprendizaje.
"""
import threading
import time
import logging
from typing import Dict, Any
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

class EdgeMonitor(threading.Thread):
    """
    Monitor autónomo que detecta inconsistencias entre módulos.
    Corre cada 60 segundos verificando sincronización entre SignalFactory, Executor y Scanner.
    """
    
    def __init__(self, storage: StorageManager, interval_seconds: int = 60):
        super().__init__(daemon=True)
        self.storage = storage
        self.interval_seconds = interval_seconds
        self.running = True
        self.name = "EdgeMonitor"
        
    def run(self):
        """Loop principal del monitor"""
        logger.info("🧠 EDGE Monitor started - checking for inconsistencies every 60s")
        
        while self.running:
            try:
                self._check_inconsistencies()
            except Exception as e:
                logger.error(f"Error in EDGE Monitor: {e}")
            
            time.sleep(self.interval_seconds)
    
    def stop(self):
        """Detener el monitor"""
        self.running = False
        logger.info("🧠 EDGE Monitor stopped")
    
    def _check_inconsistencies(self):
        """Verificar inconsistencias entre módulos"""
        # Contar señales generadas en los últimos 60s
        generated_count = self._count_recent_signals()
        
        # Contar señales ejecutadas en los últimos 60s
        executed_count = self._count_recent_executed_signals()
        
        # Si hay discrepancia significativa (>10% o >1), investigar
        if generated_count > executed_count + max(1, generated_count * 0.1):
            self._investigate_inconsistency(generated_count, executed_count)
    
    def _count_recent_signals(self) -> int:
        """Contar señales generadas en los últimos 60s"""
        conn = self.storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM signals 
                WHERE timestamp >= datetime('now', '-60 seconds')
            """)
            return cursor.fetchone()[0]
        finally:
            self.storage._close_conn(conn)
    
    def _count_recent_executed_signals(self) -> int:
        """Contar señales ejecutadas en los últimos 60s"""
        conn = self.storage._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM signals 
                WHERE status = 'EXECUTED' 
                AND timestamp >= datetime('now', '-60 seconds')
            """)
            return cursor.fetchone()[0]
        finally:
            self.storage._close_conn(conn)
    
    def _investigate_inconsistency(self, generated: int, executed: int):
        """Investigar inconsistencia y generar informe"""
        # Simulación de investigación (en producción parsear logs)
        investigation = {
            "signal_factory_logs": "Señales generadas correctamente",
            "executor_logs": f"Ejecutadas {executed} de {generated}",
            "scanner_logs": "Scanner operativo"
        }
        
        # Generar aprendizaje
        detection = f"Inconsistencia detectada: {generated} señales generadas vs {executed} ejecutadas en 60s"
        action_taken = "Monitoreo continuo activado"
        learning = f"Posible bottleneck en Executor. Ratio ejecución: {executed/generated:.2f} si generated > 0"
        
        # Guardar en EDGE learning
        self.storage.save_edge_learning(
            detection=detection,
            action_taken=action_taken,
            learning=learning,
            details=f"Investigación: {investigation}"
        )
        
        logger.warning(f"🚨 EDGE Inconsistency detected: {detection}")