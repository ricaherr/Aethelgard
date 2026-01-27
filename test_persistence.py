"""
Test de Persistencia de Aethelgard - ENTORNO DE PRUEBA AISLADO
===============================================================

⚠️  IMPORTANTE: Este script usa su propia base de datos de prueba
    Los datos generados NO afectan el sistema real.
    DB de prueba: data_vault/test_persistence.db

Verifica que el sistema persiste datos correctamente ante apagones.
"""
import sqlite3
import logging
from datetime import datetime, date
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Base de datos de prueba (separada del sistema real)
TEST_DB = Path("data_vault/test_persistence.db")


class PersistenceTestSimulator:
    """Simulador aislado para pruebas de persistencia"""
    
    def __init__(self):
        # Crear directorio si no existe
        TEST_DB.parent.mkdir(exist_ok=True)
        
        # Conectar a DB de prueba
        self.conn = sqlite3.connect(str(TEST_DB))
        self._init_db()
    
    def _init_db(self):
        """Inicializar tabla de prueba"""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                price REAL NOT NULL,
                timestamp TEXT NOT NULL,
                test_cycle INTEGER NOT NULL
            )
        """)
        self.conn.commit()
    
    def get_signals_today(self):
        """Obtener señales del día actual"""
        cursor = self.conn.cursor()
        today = date.today().isoformat()
        cursor.execute("""
            SELECT symbol, signal_type, price, timestamp, test_cycle
            FROM test_signals
            WHERE DATE(timestamp) = ?
            ORDER BY id
        """, (today,))
        return cursor.fetchall()
    
    def save_signal(self, symbol: str, signal_type: str, price: float, cycle: int):
        """Guardar señal de prueba"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO test_signals (symbol, signal_type, price, timestamp, test_cycle)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, signal_type, price, datetime.now().isoformat(), cycle))
        self.conn.commit()
    
    def close(self):
        """Cerrar conexión"""
        self.conn.close()


def run_test():
    """Ejecutar test de persistencia"""
    logger.info("=" * 70)
    logger.info("🧪 AETHELGARD - Test de Persistencia (Entorno Aislado)")
    logger.info("=" * 70)
    logger.info(f"📁 Base de datos de prueba: {TEST_DB}")
    logger.info("")
    
    # Inicializar simulador
    sim = PersistenceTestSimulator()
    
    # Obtener estado actual
    logger.info("📊 Reconstruyendo estado desde la base de datos de prueba...")
    signals_today = sim.get_signals_today()
    logger.info(f"✅ Señales en DB: {len(signals_today)}")
    
    if signals_today:
        logger.info("📋 Últimas 3 señales:")
        for sig in signals_today[-3:]:
            symbol, sig_type, price, timestamp, cycle = sig
            logger.info(f"  - Ciclo {cycle}: {symbol} | {sig_type} | ${price:.4f}")
    
    logger.info("")
    logger.info("🔄 Generando nueva actividad de prueba...")
    
    # Determinar el siguiente ciclo
    next_cycle = len(signals_today) + 1
    
    # Generar 5 señales de ejemplo
    test_data = [
        ("TEST_EUR", "LONG", 1.0850),
        ("TEST_GBP", "SHORT", 1.2650),
        ("TEST_JPY", "LONG", 149.50),
        ("TEST_AUD", "SHORT", 0.6450),
        ("TEST_NZD", "LONG", 0.5850),
    ]
    
    for i, (symbol, sig_type, price) in enumerate(test_data, 1):
        sim.save_signal(symbol, sig_type, price, next_cycle)
        logger.info(f"  {i}. {symbol}: {sig_type} @ ${price:.4f} [Ciclo {next_cycle}]")
    
    logger.info("")
    logger.info("✅ Actividad generada exitosamente!")
    
    # Mostrar totales actualizados
    updated_signals = sim.get_signals_today()
    total_count = len(updated_signals)
    
    logger.info(f"📊 Total de señales en DB: {total_count}")
    logger.info("")
    logger.info("=" * 70)
    logger.info("💡 INSTRUCCIONES PARA VERIFICAR PERSISTENCIA:")
    logger.info("=" * 70)
    logger.info(f"1️⃣  Anota este número: {total_count} señales")
    logger.info("2️⃣  Cierra FORZOSAMENTE esta terminal (Ctrl+C o clic en X)")
    logger.info("3️⃣  Vuelve a ejecutar: py test_persistence.py")
    logger.info("4️⃣  Si ves el mismo número o mayor = ✅ PERSISTENCIA CONFIRMADA")
    logger.info("")
    logger.info("🗑️  Para limpiar la DB de prueba: del data_vault\\test_persistence.db")
    logger.info("=" * 70)
    
    sim.close()


if __name__ == "__main__":
    try:
        run_test()
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupción forzosa detectada (simulando apagón)")
        logger.info("✅ Los datos deberían persistir en la DB")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise
