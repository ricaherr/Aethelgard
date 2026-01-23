"""
Bridge para MetaTrader 5
Conecta estrategias de MT5 con Aethelgard via WebSocket
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
import websockets
from websockets.exceptions import ConnectionClosed

try:
    import MetaTrader5 as mt5
except ImportError:
    print("MetaTrader5 no está instalado. Instala con: pip install MetaTrader5")
    mt5 = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MT5Bridge:
    """Bridge para conectar MetaTrader 5 con Aethelgard"""
    
    def __init__(self, 
                 server_url: str = "ws://localhost:8000/ws/MT5/",
                 client_id: str = None,
                 symbol: str = "EURUSD"):
        """
        Args:
            server_url: URL del servidor Aethelgard
            client_id: ID único del cliente (por defecto usa nombre de máquina)
            symbol: Símbolo a monitorear
        """
        self.server_url = server_url
        self.client_id = client_id or f"MT5_{symbol}"
        self.symbol = symbol
        self.websocket = None
        self.is_connected = False
        self.running = False
        
        # Inicializar MT5
        if mt5 is None:
            raise ImportError("MetaTrader5 no está disponible")
        
        if not mt5.initialize():
            raise RuntimeError(f"Error inicializando MT5: {mt5.last_error()}")
        
        logger.info(f"MT5 inicializado. Versión: {mt5.version()}")
    
    async def connect(self):
        """Conecta al servidor Aethelgard"""
        try:
            full_url = f"{self.server_url}{self.client_id}"
            logger.info(f"Conectando a Aethelgard: {full_url}")
            
            self.websocket = await websockets.connect(full_url)
            self.is_connected = True
            
            logger.info("Conectado a Aethelgard exitosamente")
            
            # Enviar mensaje de inicialización
            await self.send_message({
                "type": "init",
                "client_id": self.client_id,
                "symbol": self.symbol,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error conectando a Aethelgard: {e}")
            self.is_connected = False
            raise
    
    async def disconnect(self):
        """Desconecta del servidor"""
        try:
            self.running = False
            self.is_connected = False
            
            if self.websocket:
                await self.websocket.close()
            
            logger.info("Desconectado de Aethelgard")
        except Exception as e:
            logger.error(f"Error desconectando: {e}")
        finally:
            if mt5:
                mt5.shutdown()
    
    async def send_message(self, data: dict):
        """Envía un mensaje al servidor"""
        if not self.is_connected or not self.websocket:
            return
        
        try:
            message = json.dumps(data)
            await self.websocket.send(message)
        except Exception as e:
            logger.error(f"Error enviando mensaje: {e}")
            self.is_connected = False
    
    async def receive_messages(self):
        """Recibe mensajes del servidor"""
        try:
            while self.running and self.is_connected:
                try:
                    message = await self.websocket.recv()
                    await self.process_message(message)
                except ConnectionClosed:
                    logger.warning("Conexión cerrada por el servidor")
                    self.is_connected = False
                    break
                except Exception as e:
                    logger.error(f"Error recibiendo mensaje: {e}")
                    break
        except Exception as e:
            logger.error(f"Error en receive_messages: {e}")
    
    async def process_message(self, message: str):
        """Procesa un mensaje recibido del servidor"""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "signal_processed":
                logger.info(
                    f"Señal procesada. ID: {data.get('signal_id')}, "
                    f"Régimen: {data.get('regime')}"
                )
            elif message_type == "pong":
                # Heartbeat response
                pass
            elif message_type == "error":
                logger.error(f"Error de Aethelgard: {data.get('message')}")
            else:
                logger.warning(f"Mensaje desconocido: {message_type}")
        
        except json.JSONDecodeError:
            logger.error(f"Error decodificando JSON: {message}")
        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")
    
    async def send_market_data(self):
        """Envía datos de mercado actuales"""
        try:
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                logger.warning(f"No se pudo obtener tick para {self.symbol}")
                return
            
            await self.send_message({
                "type": "market_data",
                "symbol": self.symbol,
                "price": tick.last,
                "bid": tick.bid,
                "ask": tick.ask,
                "volume": tick.volume,
                "timestamp": datetime.fromtimestamp(tick.time).isoformat()
            })
        
        except Exception as e:
            logger.error(f"Error enviando market data: {e}")
    
    async def send_signal(self, 
                         signal_type: str,
                         price: float,
                         volume: float = 0.01,
                         stop_loss: Optional[float] = None,
                         take_profit: Optional[float] = None,
                         strategy_id: Optional[str] = None):
        """
        Envía una señal de trading a Aethelgard
        
        Args:
            signal_type: 'BUY', 'SELL', 'CLOSE', 'MODIFY'
            price: Precio de la señal
            volume: Volumen/lotes
            stop_loss: Stop loss opcional
            take_profit: Take profit opcional
            strategy_id: ID de la estrategia que genera la señal
        """
        await self.send_message({
            "type": "signal",
            "connector": "MT5",
            "symbol": self.symbol,
            "signal_type": signal_type,
            "price": price,
            "timestamp": datetime.utcnow().isoformat(),
            "volume": volume,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "strategy_id": strategy_id,
            "metadata": {
                "account": mt5.account_info().login if mt5.account_info() else None,
                "terminal": "MT5"
            }
        })
    
    async def monitor_ticks(self, interval: float = 1.0):
        """
        Monitorea ticks y envía datos periódicamente
        
        Args:
            interval: Intervalo en segundos entre envíos
        """
        self.running = True
        
        while self.running:
            try:
                if self.is_connected:
                    await self.send_market_data()
                
                await asyncio.sleep(interval)
            
            except Exception as e:
                logger.error(f"Error en monitor_ticks: {e}")
                break
    
    async def run(self, tick_interval: float = 1.0):
        """
        Ejecuta el bridge (conecta y monitorea)
        
        Args:
            tick_interval: Intervalo en segundos para enviar ticks
        """
        try:
            await self.connect()
            
            # Iniciar tareas en paralelo
            receive_task = asyncio.create_task(self.receive_messages())
            monitor_task = asyncio.create_task(self.monitor_ticks(tick_interval))
            
            # Esperar a que terminen
            await asyncio.gather(receive_task, monitor_task)
        
        except KeyboardInterrupt:
            logger.info("Interrupción recibida")
        except Exception as e:
            logger.error(f"Error en run: {e}")
        finally:
            await self.disconnect()


async def main():
    """Función principal para ejecutar el bridge"""
    bridge = MT5Bridge(
        server_url="ws://localhost:8000/ws/MT5/",
        symbol="EURUSD"
    )
    
    try:
        await bridge.run(tick_interval=1.0)
    except Exception as e:
        logger.error(f"Error en main: {e}")


if __name__ == "__main__":
    asyncio.run(main())
