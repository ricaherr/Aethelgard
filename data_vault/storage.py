"""
Sistema de persistencia SQLite para Aethelgard
Registra señales y resultados para feedback loop
"""
import sqlite3
import logging
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta # Importar timedelta
from pathlib import Path

from models.signal import Signal, SignalResult, ConnectorType, SignalType, MarketRegime

logger = logging.getLogger(__name__)

# Heurística simple para determinar el tipo de mercado si no está en assets.json
def _determine_market_type_from_symbol(symbol_name: str) -> str:
    if "USD" in symbol_name or "EUR" in symbol_name or "GBP" in symbol_name or "JPY" in symbol_name or "CAD" in symbol_name or "AUD" in symbol_name or "NZD" in symbol_name or "CHF" in symbol_name:
        return "Forex"
    elif any(crypto_tag in symbol_name for crypto_tag in ["BTC", "ETH", "XRP", "LTC", "ADA", "DOGE"]):
        return "Cripto"
    elif any(future_tag in symbol_name for future_tag in ["_F", "F", "YM", "ES", "NQ", "RTY", "GC", "CL", "NG"]):
        return "Futuros"
    else:
        return "Acciones"

class StorageManager:
    """Gestiona la persistencia de señales y resultados en SQLite"""
    
    def __init__(self, db_path: str = "data_vault/aethelgard.db", assets_config_path: str = "config/assets.json"):
        """
        Args:
            db_path: Ruta al archivo de base de datos SQLite
            assets_config_path: Ruta al archivo assets.json generado por DiscoveryEngine
        """
        self.db_path = Path(db_path)
        self.assets_config_path = Path(assets_config_path)
        # Asegurar que el directorio existe (compatible con Windows)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.symbol_to_market_type_map: Dict[str, str] = {}
        self._load_assets_map()
        self._init_database()
    
    def _load_assets_map(self):
        """Carga el mapeo de símbolos a tipos de mercado desde assets.json"""
        if self.assets_config_path.exists():
            try:
                with open(self.assets_config_path, "r", encoding="utf-8") as f:
                    assets_by_market = json.load(f)
                    for market_type, assets in assets_by_market.items():
                        for asset in assets:
                            self.symbol_to_market_type_map[asset["name"]] = market_type
                logger.info("Mapeo de activos cargado desde %s", self.assets_config_path)
            except json.JSONDecodeError as e:
                logger.warning("Error decodificando assets.json: %s. Los tipos de mercado se inferirán por heurística.", e)
        else:
            logger.warning("assets.json no encontrado en %s. Los tipos de mercado se inferirán por heurística.", self.assets_config_path)

    def _get_market_type_for_symbol(self, symbol: str) -> str:
        """Obtiene el tipo de mercado para un símbolo, usando el mapa o heurística."""
        market_type = self.symbol_to_market_type_map.get(symbol)
        if market_type:
            return market_type
        # Si no está en el mapa (ej. assets.json no existe o símbolo no listado), usar heurística
        return _determine_market_type_from_symbol(symbol)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Obtiene una conexión a la base de datos"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Permite acceso por nombre de columna
        return conn
    
    def _init_database(self):
        """Inicializa las tablas base de la base de datos (señales, resultados)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Tabla de señales
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connector TEXT NOT NULL,
                symbol TEXT NOT NULL,
                market_type TEXT, -- Nuevo campo para identificar el tipo de mercado
                signal_type TEXT NOT NULL,
                price REAL NOT NULL,
                timestamp TEXT NOT NULL,
                volume REAL,
                stop_loss REAL,
                take_profit REAL,
                regime TEXT,
                strategy_id TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabla de resultados (feedback loop)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                executed BOOLEAN NOT NULL,
                execution_price REAL,
                execution_time TEXT,
                pnl REAL,
                closed_at TEXT,
                notes TEXT,
                feedback_score REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (signal_id) REFERENCES signals(id)
            )
        """)
        
        # ELIMINAR la tabla market_states genérica si existe y no está vacía (o simplemente no crearla)
        # Para evitar problemas con datos existentes, primero comprobar si existe y si tiene datos
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='market_states';")
        if cursor.fetchone():
            logger.warning("La tabla 'market_states' genérica ya existe. Se recomienda migrar los datos o eliminarla manualmente si no se necesita.")
            # Opcional: Podríamos renombrarla o archivarla. Por ahora, solo advertimos.
        
        # Los índices para market_states_TYPE se crearán dinámicamente.
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_timestamp 
            ON signals(timestamp)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_symbol 
            ON signals(symbol)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_results_signal_id 
            ON signal_results(signal_id)
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"Base de datos base inicializada: {self.db_path}")

    def _create_market_state_table_if_not_exists(self, market_type: str, cursor: sqlite3.Cursor):
        """
        Crea una tabla de estado de mercado específica para un tipo de mercado si no existe.
        """
        table_name = f"market_states_{market_type.lower()}"
        logger.debug("Verificando/creando tabla: %s", table_name)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                regime TEXT NOT NULL,
                previous_regime TEXT,
                price REAL NOT NULL,
                adx REAL,
                volatility REAL,
                sma_distance REAL,
                bias TEXT,
                atr_pct REAL,
                volatility_shock_detected BOOLEAN,
                adx_period INTEGER,
                sma_period INTEGER,
                adx_trend_threshold REAL,
                adx_range_threshold REAL,
                adx_range_exit_threshold REAL,
                volatility_shock_multiplier REAL,
                shock_lookback INTEGER,
                min_volatility_atr_period INTEGER,
                persistence_candles INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_timestamp 
            ON {table_name}(timestamp)
        """)
        
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_symbol 
            ON {table_name}(symbol)
        """)
        
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{table_name}_regime 
            ON {table_name}(regime)
        """)
    
    def save_signal(self, signal: Signal) -> int:
        """
        Guarda una señal en la base de datos
        
        Args:
            signal: Objeto Signal a guardar
        
        Returns:
            int: ID de la señal guardada
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Obtener el tipo de mercado del símbolo de la señal
            market_type = self._get_market_type_for_symbol(signal.symbol)
            
            cursor.execute("""
                INSERT INTO signals (
                    connector, symbol, market_type, signal_type, price, timestamp,
                    volume, stop_loss, take_profit, regime, strategy_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.connector.value,
                signal.symbol,
                market_type, # Guardar el tipo de mercado con la señal
                signal.signal_type.value,
                signal.price,
                signal.timestamp.isoformat(),
                signal.volume,
                signal.stop_loss,
                signal.take_profit,
                signal.regime.value if signal.regime else None,
                signal.strategy_id,
                str(signal.metadata) if signal.metadata else None
            ))
            
            signal_id = cursor.lastrowid
            conn.commit()
            logger.debug(f"Señal guardada con ID: {signal_id} para tipo de mercado: {market_type}")
            return signal_id
        
        except Exception as e:
            conn.rollback()
            logger.error(f"Error guardando señal: {e}")
            raise
        finally:
            conn.close()
    
    def save_result(self, result: SignalResult) -> int:
        """
        Guarda el resultado de una señal (feedback loop)
        
        Args:
            result: Objeto SignalResult a guardar
        
        Returns:
            int: ID del resultado guardado
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO signal_results (
                    signal_id, executed, execution_price, execution_time,
                    pnl, closed_at, notes, feedback_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.signal_id,
                result.executed,
                result.execution_price,
                result.execution_time.isoformat() if result.execution_time else None,
                result.pnl,
                result.closed_at.isoformat() if result.closed_at else None,
                result.notes,
                result.feedback_score
            ))
            
            result_id = cursor.lastrowid
            conn.commit()
            logger.debug(f"Resultado guardado con ID: {result_id}")
            return result_id
        
        except Exception as e:
            conn.rollback()
            logger.error(f"Error guardando resultado: {e}")
            raise
        finally:
            conn.close()
    
    def get_signal(self, signal_id: int) -> Optional[Dict]:
        """Obtiene una señal por su ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_recent_signals(self, limit: int = 100) -> List[Dict]:
        """
        Obtiene las señales más recientes
        
        Args:
            limit: Número máximo de señales a retornar
        
        Returns:
            Lista de señales como diccionarios
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM signals 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_signals_by_symbol(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Obtiene señales filtradas por símbolo"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM signals 
            WHERE symbol = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (symbol, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_signal_with_result(self, signal_id: int) -> Optional[Dict]:
        """Obtiene una señal con su resultado asociado"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.*, sr.executed, sr.execution_price, sr.execution_time,
                   sr.pnl, sr.closed_at, sr.notes, sr.feedback_score
            FROM signals s
            LEFT JOIN signal_results sr ON s.id = sr.signal_id
            WHERE s.id = ?
        """, (signal_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_statistics(self) -> Dict:
        """Obtiene estadísticas generales del sistema"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Total de señales
        cursor.execute("SELECT COUNT(*) as total FROM signals")
        stats['total_signals'] = cursor.fetchone()['total']
        
        # Señales por conector
        cursor.execute("""
            SELECT connector, COUNT(*) as count 
            FROM signals 
            GROUP BY connector
        """)
        stats['signals_by_connector'] = {row['connector']: row['count'] 
                                         for row in cursor.fetchall()}
        
        # Señales por régimen
        cursor.execute("""
            SELECT regime, COUNT(*) as count 
            FROM signals 
            WHERE regime IS NOT NULL
            GROUP BY regime
        """)
        stats['signals_by_regime'] = {row['regime']: row['count'] 
                                      for row in cursor.fetchall()}
        
        # Resultados ejecutados
        cursor.execute("""
            SELECT COUNT(*) as total, 
                   AVG(pnl) as avg_pnl,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades
            FROM signal_results 
            WHERE executed = 1
        """)
        result_row = cursor.fetchone()
        if result_row['total']:
            stats['executed_signals'] = {
                'total': result_row['total'],
                'avg_pnl': result_row['avg_pnl'],
                'winning_trades': result_row['winning_trades'],
                'win_rate': result_row['winning_trades'] / result_row['total']
            }
        else:
            stats['executed_signals'] = None
        
        conn.close()
        return stats
    
    def log_market_state(self, state_data: Dict) -> int:
        """
        Guarda el estado completo del mercado cuando se detecta un cambio de régimen.
        Incluye todos los indicadores internos para permitir el aprendizaje continuo.
        Los datos se guardan en tablas separadas por tipo de mercado.
        
        Args:
            state_data: Diccionario con los siguientes campos:
                - symbol: Símbolo del instrumento
                - timestamp: Timestamp del estado
                - regime: Régimen actual detectado
                - previous_regime: Régimen anterior (opcional)
                - price: Precio actual
                - adx: Valor de ADX
                - volatility: Volatilidad calculada
                - sma_distance: Distancia a SMA (opcional)
                - bias: Sesgo del mercado (BULLISH/BEARISH, opcional)
                - atr_pct: ATR como porcentaje (opcional)
                - volatility_shock_detected: Si se detectó shock (opcional)
                - adx_period: Período ADX usado
                - sma_period: Período SMA usado
                - adx_trend_threshold: Umbral ADX para TREND
                - adx_range_threshold: Umbral ADX para RANGE
                - adx_range_exit_threshold: Umbral ADX para salir de TREND
                - volatility_shock_multiplier: Multiplicador de shock
                - shock_lookback: Lookback para shock
                - min_volatility_atr_period: Período ATR mínimo
                - persistence_candles: Velas de persistencia
        
        Returns:
            int: ID del estado guardado
        """
        symbol = state_data.get('symbol')
        if not symbol:
            raise ValueError("El campo 'symbol' es requerido para log_market_state.")
            
        market_type = self._get_market_type_for_symbol(symbol)
        table_name = f"market_states_{market_type.lower()}"

        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            self._create_market_state_table_if_not_exists(market_type, cursor) # Asegurar que la tabla exista
            
            cursor.execute(f"""
                INSERT INTO {table_name} (
                    symbol, timestamp, regime, previous_regime, price,
                    adx, volatility, sma_distance, bias, atr_pct,
                    volatility_shock_detected, adx_period, sma_period,
                    adx_trend_threshold, adx_range_threshold, adx_range_exit_threshold,
                    volatility_shock_multiplier, shock_lookback, min_volatility_atr_period,
                    persistence_candles
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                state_data.get('symbol'),
                state_data.get('timestamp'),
                state_data.get('regime'),
                state_data.get('previous_regime'),
                state_data.get('price'),
                state_data.get('adx'),
                state_data.get('volatility'),
                state_data.get('sma_distance'),
                state_data.get('bias'),
                state_data.get('atr_pct'),
                state_data.get('volatility_shock_detected', False),
                state_data.get('adx_period'),
                state_data.get('sma_period'),
                state_data.get('adx_trend_threshold'),
                state_data.get('adx_range_threshold'),
                state_data.get('adx_range_exit_threshold'),
                state_data.get('volatility_shock_multiplier'),
                state_data.get('shock_lookback'),
                state_data.get('min_volatility_atr_period'),
                state_data.get('persistence_candles')
            ))
            
            state_id = cursor.lastrowid
            conn.commit()
            logger.debug(f"Estado de mercado guardado en {table_name} con ID: {state_id}")
            return state_id
        
        except Exception as e:
            conn.rollback()
            logger.error(f"Error guardando estado de mercado en {table_name}: {e}")
            raise
        finally:
            conn.close()
    
    def get_market_states(self, limit: int = 1000, symbol: Optional[str] = None) -> List[Dict]:
        """
        Obtiene los estados de mercado guardados para análisis
        
        Args:
            limit: Número máximo de registros a retornar
            symbol: Filtrar por símbolo (opcional)
        
        Returns:
            Lista de estados de mercado como diccionarios
        """
        table_name = f"market_states_{market_type.lower()}"
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Verificar si la tabla existe antes de intentar consultarla
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';")
            if not cursor.fetchone():
                logger.warning("La tabla %s no existe.", table_name)
                return []
                
            if symbol:
                cursor.execute(f"""
                    SELECT * FROM {table_name}
                    WHERE symbol = ?
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (symbol, limit))
            else:
                cursor.execute(f"""
                    SELECT * FROM {table_name}
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error obteniendo estados de mercado de {table_name}: {e}")
            raise
        finally:
            conn.close()
